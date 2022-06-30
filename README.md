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

**NOTA:** El acd1 deberá haber enviado a todas las salas `!wa set-relay` y un `!wa set-pl @acd1:dominio_cliente.com 100`.

**NOTA:** Mi recomendación es verificar varias veces que el acd1 se unió a todas las salas del acd viejo.

<br>

- Deberá iniciarse sesión con el acd1 en la sala de control, hacer `!wa login` y escanear el nuevo qr, el acd1 debería ser el nuevo anfitrión de todas las salas del acd viejo.
- Ahora que ya tenemos al acd1 en las salas y conectado, podemos sacar al acd viejo de todas las salas donde él se encuentre, absolutamente todas.
- Se debe ingresar a la base de datos del bridge, en la tabla portal debemos ejecutar el siguiente comando.
```sql
UPDATE portal SET relay_user_id = '@acd1:dominio_cliente.com' WHERE relay_user_id = '@acd:dominio_cliente.com';
```
- En teoría esto es todo para empezar a operar 😜.
<br>
## INSTALACIÓN:

- Debera cambiar el siguiente campo en el archivo de configuración del bridge de `mautrix-whatsapp`.
```yaml
    permissions:
        '*': relay
        '@acd:dominio_cliente.com': admin
        '@supervisor:dominio_cliente.com': admin

    # Debe cambiarla a

    permissions:
        'dominio_cliente.com': admin
```
- Crear un usuario administrador del synapse, para monitorear el AppService
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
- Abrir el archivo `docker-compose.yml`
```bash
vim /mnt/shared/matrix/dominio_cliente.com/docker-compose.yml
```
- Agregar la siguiente sección:
```yaml
  nombrecliente-acd:
    image: ikonoim/acd-appservice:stable
    volumes:
      - /var/data/${TOP_DOMAIN?Variable not set}/acd_data:/data
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
        - traefik.http.routers.acd-${SERVICE?Variable not set}.rule=Host(`cliente-api.ikono.im`)
        - traefik.http.routers.acd-${SERVICE?Variable not set}.entrypoints=https
        - traefik.http.routers.acd-${SERVICE?Variable not set}.tls=true
        - traefik.http.services.acd-${SERVICE?Variable not set}.loadbalancer.server.port=29666
    logging:
      driver: json-file
      options:
        max-size: 20m
        max-file: 10
    networks:
      - traefik-public
      - default
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
    address: http://synapse:8008

    domain: dominio_cliente.com
...
appservice:
    # Definir aquí el nombre del servicio
    address: http://nombrecliente-acd:29666
    # La base de datos debe ser creada previamente
    # Si es creada en la red de docker, utilizar los alises
    # ó el nombre del contendor de postgres
    database: postgres://synapse:onokisoft@postgres/acd_db
...
    # Este ID debe ser diferente para cada appservice (si hay más de un appservice, deben tener id diferentes)
    id: acd_az
...
    # Este bot_username debe ser diferente para cada appservice (si hay mas de un appservice, deben tener bot_username diferentes)
    bot_username: acd
...
bridge:
    # Este username_template debe ser diferente para cada appservice (si hay mas de un appservice, deben tener username_template diferentes)
    username_template: "acd{userid}"

    # Para invitar al admin a las salas de control
    provisioning:
        # Admin of the rooms created by provisioning
        admin_provisioning: "@admin:dominio_cliente.com"
    ...
acd:
    # Sala de control del acd que vamos a reemplazar,
    # si la instalación es nueva, entonces no coloque nada
    control_room_id: "!foo:dominio_cliente.com"
    # Si hay solo un menubot, se debería tener menubot.active en true
    # en caso contrario en false
    menubot:
        active: true
        user_id: "@menubot:dominio_cliente.com"
        command_prefix: "!menubot"

    menubots:
      "@menubota:dominio_cliente.com":
        user_prefix: "gswA"
        command_prefix: "!menubotA"
        is_guest: true

      "@menubotb:dominio_cliente.com":
        user_prefix: "gswB"
        command_prefix: "!menubotB"
    ...
    # Para invitar a los supervisores, debe agregarlos a esta lista
    # y dejar en true supervisors_to_invite.invite
    supervisors_to_invite:
        power_level: 99
        # If active is true, then invite users to invitees
        invite: false
        invitees:
            - "@supervisor:dominio_cliente.com"
            - "@admin:dominio_cliente.com"
bridges:
  mautrix:
    # Mautrix UserID
    # Aquí debe poner el user_id del usuario del bridge
    mxid: "@mx_whatsappbot:dominio_cliente.com"
    # Prefix to be listened by bridge
    prefix: "!wa"
    # Prefix for users created
    user_prefix: "mxwa"
    # Settings for provisioning API
    # Esta información la pueden obtener del archivo de configuración del brige
    # en la seccion provisioning
    provisioning:
        url_base: "http://172.17.0.1:29665/_matrix/provision"
        shared_secret: "gZv0kzqrZ4PFHb614IusrTuhPTDhUalJWq9xXL1K9OKBIs2bsxGD6SUOkgyN4OWP"
```
-  Ahora que tiene todos los campos configurados, se debe generar el `config.yaml`:
```bash
docker run --rm -v $(pwd):/data ikonoim/acd-appservice:stable
```
- Copiar el `registration.yaml` en la ruta `/var/data/dominio_cliente.com/synapse`
**NOTA:** Todos los `registrations` **deben ser diferentes**, por ejemplo **registration`-acd`.yaml**, **NO deben tener el mismo nombre**.
```bash
cp registration.yaml /var/data/dominio_cliente.com/synapse/registration-acd.yaml
```

- Registrar el appservice en el `homeserver.yaml`:
```bash
vim /var/data/dominio_cliente.com/synapse/homeserver.yaml
```
- Buscar la sección `app_service_config_files`, si está comentada, des comentarla.
- Agregan el registration en la lista de appservices:
```bash
app_service_config_files:
  - /data/registration-acd.yaml
```
- Eliminar el servicio del synapse `dominio_clientecom-synapse`
```bash
docker service rm dominio_clientecom-synapse
```
- Ir a la carpeta:
```bash
cd /mnt/shared/matrix/dominio_cliente.com/
```
- Correr reiniciar los servicios:
```bash
docker-compose config | docker stack deploy -c - $(basename $PWD | tr -d '.')
```
