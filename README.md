# ACD AppService

**NOTA:** Se necesita tener previamente un synapse instalado con un bridge de `mautrix-whatsapp`.

## MIGRACIÓN ACD VIEJO:

- Lo primero es parar el servicio del acd viejo
```bash
docker service rm nombrecliente-acd
```
- Con el acd viejo enviar a la sala de control el siguiente mensaje `!wa logout` (ó `!wa1`, `!wa2`, dependiendo de la instalación del bridge).
- Ahora se debe seguir la instalación de este nuevo acd
- Con la instalación completa, debes crear un usuario enviando una solicitud al endpoint de la
provisioning del nuevo acd:
```curl
curl -X POST -d '{"user_email":"correo-cliente@test.com", "control_room_id":"!foo:dominio_cliente.com"}' -H "Content-Type: application/json" https://cliente-api.ikono.im/provision/v1/create_user
```
- Ahora debería unir al nuevo usuario acd1 en las salas donde este el acd viejo

<br>

**NOTA:** El acd1 deberá haber enviado a las salas de clientes los siguientes comandos`!wa set-relay` y un `!wa set-pl @acd1:dominio_cliente.com 100`.

**NOTA:** Mi recomendación es verificar varias veces que el acd1 se unió a todas las salas del acd viejo.

<br>

- Deberá iniciar sesión con el acd1 en la sala de control, hacer `!wa login` y escanear el nuevo qr, el acd1 debería ser el nuevo anfitrión de todas las salas del acd viejo.
- Ahora que ya tenemos al acd1 en las salas y conectado a WhatsApp, podemos sacar al acd viejo de todas las salas donde él se encuentre, absolutamente todas.
- Se debe ingresar a la base de datos del bridge, en la tabla `portal` debemos ejecutar el siguiente comando.
```sql
UPDATE portal SET relay_user_id = '@acd1:dominio_cliente.com' WHERE relay_user_id = '@acd:dominio_cliente.com';
```
- En teoría esto es todo para empezar a operar 😜.
<br>

## INSTALACIÓN:

- Debera cambiar el siguiente campo en el archivo de configuración del bridge de `mautrix-whatsapp`.
```yaml
    provisioning:
        shared_secret: generate

    # y

    permissions:
        '*': relay
        '@acd:dominio_cliente.com': admin
        '@supervisor:dominio_cliente.com': admin

    # Debe cambiarla a

    permissions:
        'dominio_cliente.com': admin
```
- Se debe eliminar el servicio del `mautrix-whatsapp` y volver hacer el despliegue para que se genere el shared_secret.
- Crear un usuario administrador del synapse, para monitorear el AppService
<br>

**NOTA:** Este comando debe ser ejecutado en el nodo donde está instalado el cliente
```bash
docker exec -it contenedor-synapse register_new_matrix_user -u admin -a -c /data/homeserver.yaml http://localhost:8008
```
- Crear una carpeta para almacenar la data del appservice:
```bash
mkdir /var/data/dominio_cliente.com/acd_data/
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
  cliente-acd:
      image: ikonoim/acd-appservice:stable
      volumes:
        - /var/data/${TOP_DOMAIN?Variable not set}/acd_data:/data
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
cd /var/data/dominio_cliente.com/acd_data/
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
appservice:
...
    puppet_password: contraseña_segura
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
    # Prefix to be listened by bridge
    prefix: "!ig"
    # Prefix for users created
    user_prefix: "ig"
    # create_portal_command: "pm"
    send_template_command: ""
    # Postfix to identify a customer
    postfix_template: "(IG)"
    set_permissions: "set-pl {mxid} {power_level}"
    set_relay: "set-relay"
```
-  Ahora que tiene todos los campos configurados, se debe generar el `registration.yaml`:
```bash
docker run --rm -v $(pwd):/data ikonoim/acd-appservice:stable
```
- Copiar el `registration.yaml` en la ruta `/var/data/dominio_cliente.com/synapse`
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
- Eliminar el servicio del synapse `dominio_clientecom-synapse`
```bash
docker service rm dominio_clientecom-synapse
```
- Ir a la carpeta:
```bash
cd /mnt/shared/matrix/dominio_cliente.com/
```
- El menubot debe ignorar un listado de acd* en la sección bots
- Reiniciar los servicios:
```bash
docker-compose config | docker stack deploy -c - $(basename $PWD | tr -d '.')
```
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
curl -X POST -d '{"user_email":"correo-cliente@test.com", "menubot_id":"@menubot:dominio_cliente.com"}' -H "Content-Type: application/json" https://cliente-api.ikono.im/provision/v1/create_user
```

`instagram`
```curl
curl -X POST -d '{"user_email":"correo-cliente@test.com", "menubot_id":"@menubot:dominio_cliente.com", "bridge":"instagram"}' -H "Content-Type: application/json" https://cliente-api.ikono.im/provision/v1/create_user
```
- NOTA: la contraseña de estos usuarios esta en el config `puppet_password`

- Invitar al menubot y a los agentes a la nueva sala de control

## ACD Modo API

# Envia un mensaje	
Endpoint: `/provision/v1/send_message`
Metodo: `POST`
Datos requeridos:
- `user_email`: foo@foo.com.co
- `phone`: 573123456789
- `msg_type`: text
- `message`: Hola Mundo!!

Ejemplo: 

```curl
curl -X POST -d '{"user_email":"foo@foo.com.co", "phone":"573123456789", "msg_type":"text", "message":"Hola Mundo!!"}' -H "Content-Type: application/json" https://sender.z.ikono.im/provision/v1/send_message
```

**NOTA**:  Actualmente, solo se pueden enviar mensajes tipo `text`
**NOTA**:  El campo `phone` debe tener el formato del pais

## Respuestas:
#### 1 -  El mensaje ha sido enviado correctamente
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
---

# Verificación de lectura
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
