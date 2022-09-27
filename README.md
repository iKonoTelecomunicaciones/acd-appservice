# ACD AppService

**NOTA:** Se necesita tener previamente un synapse instalado con un bridge de `mautrix-whatsapp`.

## MIGRACIÓN ACD VIEJO:

- Actualizar el synapse a la versión 1.54.0 (docker image `ikonoim/synapse:v1.54.0`)

- Si usted viene de la versión del bridge 0.2.4, debe cambiar primero esto en el config del bridge:
```yaml
    provisioning:
        shared_secret: disable

    # CAMBIAR A

    provisioning:
        shared_secret: generate
```

- Actualizar el bridge de mautrix a la versión 0.6.0 (docker image `dock.mau.dev/mautrix/whatsapp:v0.6.0`)

- Eliminar el servicio del `mautrix-whatsapp` y volver hacer el despliegue para que se genere el shared_secret.

- Crear un usuario administrador del synapse para monitorear el AppService, de la siguiente manera:
**NOTA:** Este comando debe ser ejecutado en el nodo donde está instalado el cliente
```bash
docker exec -it contenedor-synapse register_new_matrix_user -u admin -a -c /data/homeserver.yaml http://localhost:8008
```

- Con un usuario admin o supervisor enviar a la sala de control el siguiente mensaje `!acd br-cmd !wa logout` (ó `!wa1`, `!wa2`, dependiendo de la instalación del bridge).

- Ahora se debe parar el servicio del acd viejo
```bash
docker service rm nombrecliente-acd
```

- Ahora se debe seguir la instalación de este nuevo acd

- Eliminar la sala de control del menubot y del frontend

- Debera configurar la provisioning de la API del acd en el Element en agente y supervisor
```json
    "acd_provisioning_api": {
      "API_PROTOCOL": "https",
        "API_HOST": "cliente.z.ikono.im/provision",
        "API_PORT": "",
        "API_VERSION": "v1"
    }
```

- Con la instalación completa, debes crear un usuario enviando una solicitud al endpoint de la
provisioning del nuevo acd:

```curl
curl -X POST -d '{"user_email":"acd1@dominio_cliente.com", "control_room_id":"!foo:dominio_cliente.com"}' -H "Content-Type: application/json" https://cliente.z.ikono.im/provision/v1/create_user
```
- Invitar el acd1 a todas las salas de clientes. No invitarlo a las salas de colas. Para esto se usa el script.

<br>

**NOTA:** El acd1 deberá haber enviado a las salas de clientes los siguientes comandos`!wa set-relay` y un `!wa set-pl @acd1:dominio_cliente.com 100`.

**NOTA:** Mi recomendación es verificar varias veces que el acd1 se unió a todas las salas del acd viejo.

<br>

- Ahora que ya tenemos al acd1 en las salas de clientes, debemos sacar al acd viejo de todas las salas de clientes. Dejar el acd viejo en las salas de colas.

- Ingresar a la base de datos del bridge, `\c mautrix_whatsapp` y ejecutar el siguiente comando:
```sql
UPDATE portal SET relay_user_id = '@acd1:dominio_cliente.com' WHERE relay_user_id = '@acd:dominio_cliente.com';
```

- Ejecutar `!acd br_cmd !wa login` en la sala de control del acd1 y escanear el nuevo qr, el acd1 debería ser el nuevo anfitrión de todas las salas del acd viejo.

- En teoría esto es todo para empezar a operar 😜.
<br>

## INSTALACIÓN:
- Eliminar la sala de control del menubot y del frontend
- Debera cambiar el siguiente campo en el archivo de configuración del bridge de `mautrix-whatsapp`.
```yaml
    permissions:
        '*': relay
        '@acd:dominio_cliente.com': admin
        '@supervisor:dominio_cliente.com': admin

    # DEBE CAMBIAR A

    permissions:
        'dominio_cliente.com': admin
```
<br>

- Crear una carpeta para almacenar la data del appservice:
```bash
mkdir /mnt/shared/matrix/dominio_cliente.com/acd_data/
```
- Crear una bd para el appservice (en el mismo contenedor de postgres donde está la bd del synapse):
```sql
CREATE DATABASE acd_db ENCODING 'UTF8' LC_COLLATE='C' LC_CTYPE='C' template=template0 OWNER synapse;
```
- Agregar la siguiente variable de entorno al `.env` del cliente
```bash
ACD_API_DOMAIN=cliente-tal.z.ikono.im
```

- Abrir el archivo `docker-compose.yml`
```bash
vim /mnt/shared/matrix/dominio_cliente.com/docker-compose.yml
```
- Agregar la siguiente sección:
```yaml
  cliente-acd-as:
      image: ikonoim/acd-appservice:stable
      volumes:
        - /mnt/shared/matrix/${TOP_DOMAIN?Variable not set}/acd_data:/data
      networks:
        traefik-public:
        default:
          aliases:
            - acd-as
      deploy:
        replicas: 1
        placement:
          constraints:
            - node.hostname == ${DEPLOY_SERVER?Variable not set}
        labels:
          - traefik.enable=true
          - traefik.docker.network=traefik-public
          - traefik.constraint-label=traefik-public
          # This block sets the routers
          - traefik.http.routers.acd-${SERVICE?Variable not set}.rule=Host(`${ACD_API_DOMAIN?Variable not set}`)
          - traefik.http.routers.acd-${SERVICE?Variable not set}.entrypoints=https
          - traefik.http.routers.acd-${SERVICE?Variable not set}.tls=true
          - traefik.http.services.acd-${SERVICE?Variable not set}.loadbalancer.server.port=29601
      logging:
        driver: json-file
        options:
          max-size: 20m
          max-file: "10"
```
- Ir la carpeta:
```bash
cd /mnt/shared/matrix/dominio_cliente.com/acd_data/
```

- Ejecutar un comando que creará el `config.yaml`
```bash
docker run --rm -v $(pwd):/data ikonoim/acd-appservice:stable
```

- Abra el archivo generado `config.yaml` y edite los siguientes campos:
```bash
homeserver:
...
    domain: dominio_cliente.com
...

bridge:
...
    # Para invitar al admin a las salas de control
    provisioning:
        # Admin of the rooms created by provisioning
        admin: "@admin:dominio_cliente.com"
    ...
acd:
    # Para invitar a los supervisores, debe agregarlos a esta lista
    # y dejar en true supervisors_to_invite.invite
    supervisors_to_invite:
        power_level: 99
        # If active is true, then invite users to invitees
        invite: false
        invitees:
            - "@supervisor:dominio_cliente.com"
bridges:
  mautrix:
    # Mautrix UserID
    # Aquí debe poner el user_id del usuario del bridge
    mxid: "@mx_whatsappbot:dominio_cliente.com"
    # Settings for provisioning API
    # Esta información la pueden obtener del archivo de configuración del brige
    # en la seccion provisioning
    provisioning:
        url_base: "http://mautrix-whatsapp:29318/_matrix/provision"
        shared_secret: "copiar_shared_secret_del_provisioning_del_config_del_mautrix"
  instagram:
    # Instagram UserID
    mxid: "@instagrambot:dominio_cliente.com"
    provisioning:
        url_base: "http://mautrix-instagram:29320/_matrix/provision"
        shared_secret: "copiar_shared_secret_del_provisioning_del_config_del_instagram"
  gupshup:
    # Gupshup UserID
    mxid: "@gs_whatsappbot:dominio_cliente.com"
    provisioning:
        url_base: "http://gupshup:29324/_matrix/provision"
        shared_secret: "copiar_shared_secret_del_provisioning_del_config_del_gupshup"

ikono_api:
  password: "contraseña del acd principal"
```
-  Ahora que tiene todos los campos configurados, se debe generar el `registration.yaml`:
```bash
docker run --rm -v $(pwd):/data ikonoim/acd-appservice:stable
```

- Agregar a los namespaces del `registration.yaml` las dos siguientes secciones:
```yaml
    - exclusive: false
      regex: '@menubot:dominio_cliente\.com'
    - exclusive: false
      regex: '@supervisor:dominio_cliente\.com'
```

- Entrar al nodo donde está instalado el cliente y copiar el `registration.yaml` en la ruta `/var/data/dominio_cliente.com/synapse`
```bash
cp registration.yaml /var/data/dominio_cliente.com/synapse/registration-acd-as.yaml
```

- Registrar el appservice en el `homeserver.yaml`:
```bash
vim /var/data/dominio_cliente.com/synapse/homeserver.yaml
```
- Buscar la sección `app_service_config_files`, si está comentada, des comentarla.
- Agregan el registration en la lista de appservices:
```bash
app_service_config_files:
  - /data/registration-acd-as.yaml
```
- Reiniciar el servicio del synapse `dominio_clientecom-synapse`
```bash
docker service rm dominio_clientecom-synapse
```
- Ir a la carpeta:
```bash
cd /mnt/shared/matrix/dominio_cliente.com/
```
- Agregar a la sección `bots` del `menubot_config.yaml` el listado de puppets según la cantidad de lineas que tenga el cliente, y agrgar la url del acd para las peticiones de las salas de control
```yaml
...
bots:
  ...
  - "@acd1:dominio_cliente.com"
  - "@acd2:dominio_cliente.com"
  ...
...
# Endpoint base de la provisioning del acd-as
acd_as:
  base_url: "http://acd-as:29601/provision"
```
- Eliminar el servicio del menubot `dominio_clientecom-menubot`
- Reiniciar los servicios:
```bash
docker-compose config | docker stack deploy -c - $(basename $PWD | tr -d '.')
```
**NOTA:** Los acd* no aceptarán invitaciones a salas donde ya haya ingresado previamente un acd*, esto puede afectarlos en salas de colas.
- Por cada linea de whatsapp o aplicación de instagram se debe ejecutar el siguiente endpoint, el cual se encarga de las siguientes tareas:
  - Crear el usuario acd* (puppet) encargado del manejo de la linea
  - Crear la sala de control de la linea o canal
  - Invitar al bridge bot que corresponde por linea
  - Opcionalmente invita al menubot si se envia el parámetro en la petición
  - Si ya existe una sala de control, tambien se puede enviar opcionalmente usando el parámetro `control_room_id`
  - Por defecto el bridge usado en la sala de control es el bridge de web-whatsapp. Si la sala de control es de otro canal se debe especificar utilizando el parámetro `bridge`:
    - `mautrix`
    - `instagram`
    - `gupshup`
  - Puedes enviar el bridge que quieres invitar usando `bridge`

- El menubot debe estar funcionando

`mautrix`
```curl
curl -X POST -d '{"user_email":"acd1@dominio_cliente.com", "menubot_id":"@menubot:dominio_cliente.com"}' -H "Content-Type: application/json" https://cliente.z.ikono.im/provision/v1/create_user
```

`instagram`
```curl
curl -X POST -d '{"user_email":"acd1@dominio_cliente.com", "menubot_id":"@menubot:dominio_cliente.com", "bridge":"instagram"}' -H "Content-Type: application/json" https://cliente.z.ikono.im/provision/v1/create_user
```

`gupshup`
```curl
curl -X POST -d '{"user_email":"acd1@dominio_cliente.com", "menubot_id":"@menubot:dominio_cliente.com", "bridge":"gupshup"}' -H "Content-Type: application/json" https://cliente.z.ikono.im/provision/v1/create_user
```

- NOTA: la contraseña de estos usuarios esta en el config `puppet_password`

- Si la sala de control ya existía se debe salir el `@acd:dominio_cliente.com` de esta sala y de todas las salas en las que se encuentre (debe quedar sin salas).
- Se debe invitar a al `acd*` a las salas de colas y hacerlo admin.
- Invitar al menubot y a los agentes a las nuevas salas de control


# iKono Chat API

#### Registrar una cuenta

Endpoint: `provision/v1/create_user`

Metodo: `POST`

Datos requeridos:

    user_email: foo@foo.com.co

Ejemplo:

```curl
curl -X POST -d '{"user_email":"foo@foo.com.co"}' -H "Content-Type: application/json" https://sender.z.ikono.im/provision/v1/create_user
```

#### Respuestas:
##### 1 -  El usuario ha sido creado

Status: `201`

Respuesta:

    {
        "user_id" : "@foo:foo.com.co",
        "control_room_id" : "!foo:foo.com.co",
        "email" : "foo@foo.com.co"
    }

##### 2 -  Email invalido

Status: `400`

Respuesta:

    {"error": "Not a valid email"}

##### 3 -  Usuario ya registrado

Status: `422`

Respuesta:

    {"error": "User already exists"}

---

#### Conectate con WhatsApp

Genera un código QR para un usuario existente con el fin de vincular el número de WhatsApp escaneando el código QR con el teléfono móvil.
Esto crea un `WebSocket`, si
no te conectas a tiempo, la conexión terminará por `timeout`.

**NOTA**: Tu conexión con el `WebSocket` te permitirá recibir información relacionada con un inicio de sesión de WhatsApp, te enviará un Qr en text, este código lo debes convertir en una imagen y cuando escanees el Qr el te enviara la información de login y luego terminará la conexión.

**NOTA**: Si deseas escanear el qr sin usar este endpoint, comunícate con soporte de iKono Chat:  soporte@ikono.com.co - [WhasApp Soporte Ikono](https://wa.me/573148901850)


Endpoint: `/provision/v1/mautrix/ws_link_phone?user_email=foo@foo.com.co`

Metodo: `GET`

##### 1 -  Qr generado

Respuesta:

    data:
        code: "2@Y0SYKO62z8tZXp9KDf4w8D/4qLioopgFtT3Bc2aSdt6Jdmg4DZlM1..."
        timeout: 60
    status: 200

##### 2 -  Login exitoso

Respuesta:

    data:
        jid: "573123456789.0:65@s.whatsapp.net"
        phone: "+573123456789"
        success: true
    status: 201

##### 3 -  Tiempo de login superado

    data:
        success: false
        error: "QR code scan timed out. Please try again."
        errcode: "login timed out"
    status: 422

#### 4 - El usuario no existe

Status: `404`

Respuesta:

    {"error": "User doesn't exist"}

---

#### Envia un mensaje

Endpoint: `/provision/v1/mautrix/send_message`

Metodo: `POST`

Datos requeridos:

    user_email: foo@foo.com.co
    phone: 573123456789
    msg_type: text
    message: Hola Mundo!!

Ejemplo:

```curl
curl -X POST -d '{"user_email":"foo@foo.com.co", "phone":"573123456789", "msg_type":"text", "message":"Hola Mundo!!"}' -H "Content-Type: application/json" https://sender.z.ikono.im/provision/v1/mautrix/send_message
```

**NOTA**:  Actualmente, solo se pueden enviar mensajes tipo `text`
**NOTA**:  El campo `phone` debe tener el formato del pais

#### Respuestas:
##### 1 -  El mensaje ha sido enviado correctamente

Status: `201`

Respuesta:

    {
      "detail": "The message has been sent (probably)",
      "event_id": "$xhm6sSrK2nCr7s5Xp09jhjy_PNqBcVnTI3dKcDdOLJ8",
      "room_id": "!JJJPEfigBmkDBIvWvF:sender.ikono.im"
    }

#### 2 - El número no existe en WhatsApp

Status: `404`

Respuesta:

    {
	  "success": false,
	  "error": "The server said +573058 is not on WhatsApp",
	  "errcode": "not on whatsapp"
	}

#### 3 - Parametros faltantes

Status: `422`

Respuesta:

	{
	  "error": "Please provide required variables"
	}

#### 4 - Error interno

Status: `500`

En este caso comunícate con soporte de iKono Chat:  soporte@ikono.com.co - [WhatsApp Soporte Ikono](https://wa.me/573148901850)

---

#### Verificación de lectura

Endpoint: `/provision/v1/read_check?event_id=xyz_123`

Metodo: `GET`

Ejemplo:

```curl
curl --location --request GET 'https://sender.z.ikono.im/provision/v1/read_check?event_id=$ZuC98SlYtdWPoKPaUeHnTO3eLJL5fVGr3vpuHOoevBk'
```

#### 1 -  Lectura del mensaje

Status: `200`

Respuesta:

	{
	  "event_id": "$kPo-UMnVUn0VvrrTvcqF1MRg7V9Nr_U1XwcmlGUykAE",
	  "room_id": "!JJJPEfigBmkDBIvWvF:sender.ikono.im",
	  "sender": "@acd3:sender.ikono.im",
	  "receiver": "+573058790290",
	  "timestamp_send": 1660331743,
	  "timestamp_read": 1660331768,
	  "was_read": true
	}

#### 2 - Mensaje no encontrado

Status: `404`

Respuesta:

    {
	    "error": "Message not found"
	}

#### 3 - Parametros faltantes

Status: `422`

Respuesta:

	{
	  "error": "Please provide required variables"
	}

#### 4 - Error interno

Status: `500`

En este caso comunícate con soporte de iKono Chat:  soporte@ikono.com.co - [WhasApp Soporte Ikono](https://wa.me/573148901850)
