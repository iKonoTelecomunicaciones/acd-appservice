# Send Appservice API (Mapi)

API que expone un recurso web para hacer login y enviar mensajes a través de WhatsApp

**NOTA:** Se necesita tener previamente un synapse instalado con un bridge de `mautrix-whatsapp`.

Pasos:

- Crear un usuario administrador del synapse, para monitorear el AppService
**NOTA:** Este comando debe ser ejecutado en el nodo donde está instalado el cliente
```bash
docker exec -it contenedor-synapse register_new_matrix_user -u admin_mapi -a -c /data/homeserver.yaml http://localhost:8008
```
- Crear una carpeta para almacenar la data del appservice:
```bash
mkdir /var/data/dominio_cliente.com/mapi/
```
- Crear una bd para el appservice (en el mismo contenedor de postgres donde está la bd del synapse):
```sql
CREATE DATABASE mapi_db ENCODING 'UTF8' LC_COLLATE='C' LC_CTYPE='C' template=template0 OWNER synapse;
```
- Abrir el archivo `docker-compose.yml`
```bash
vim /mnt/shared/matrix/dominio_cliente.com/docker-compose.yml
```
- Agregar la siguiente sección:
```yaml
  nombrecliente-mapi:
    image: ikonoim/mapi:stable
    volumes:
      - /var/data/${TOP_DOMAIN?Variable not set}/mapi:/data
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
        - traefik.http.routers.mapi-${SERVICE?Variable not set}.rule=Host(`cliente-mapi.ikono.im`)
        - traefik.http.routers.mapi-${SERVICE?Variable not set}.entrypoints=https
        - traefik.http.routers.mapi-${SERVICE?Variable not set}.tls=true
        - traefik.http.routers.mapi-${SERVICE?Variable not set}.tls.certresolver=le
        - traefik.http.services.mapi-${SERVICE?Variable not set}.loadbalancer.server.port=29666
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
cd /var/data/dominio_cliente.com/mapi/
```
- Ejecutar un comando que creará el `config.yaml`
```bash
docker run --rm -v $(pwd):/data ikonoim/mapi:stable
```
- Abra el archivo generado `config.yaml` y edite los siguientes campos:
```bash
homeserver:
    address: http://synapse:8008

    domain: dominio_cliente.com
...
appservice:
    # Definir el aquí el nombre del servicio
    address: http://nombrecliente-mapi:29666
    # La base de datos debe ser creada previamente
    # Si es creada en la red de docker, utilizar los alises
    # ó el nombre del contendor de postgres
    database: postgres://synapse:onokisoft@postgres/mapi_db
...
    # Este id debe ser diferente para cada appservice (si hay mas de un appservice, deben tener id diferentes)
    id: ik_mapi
...
    # Este bot_username debe ser diferente para cada appservice (si hay mas de un appservice, deben tener bot_username diferentes)
    bot_username: ikobot
...
bridge:
    # Este username_template debe ser diferente para cada appservice (si hay mas de un appservice, deben tener username_template diferentes)
    username_template: "ik_{userid}"
    ...
    bot_user_id: "@mx_whatsappbot:dominio_cliente.com"
    ...
    prefix: "!wa" # **NOTA:** este prefix debe adaptarse al que usa el bridge en particular
    ...
    invitees_to_rooms:
        - "@admin_mapi:dominio_cliente.com"
        - "@mx_whatsappbot:dominio_cliente.com"

```
-  Ahora que tiene todos los campos configurados, se debe generar el `registration.yaml`:
```bash
docker run --rm -v $(pwd):/data ikonoim/mapi:stable
```
- Copiar el `registration.yaml` en la ruta `/var/data/dominio_cliente.com/synapse`
**NOTA:** Todos los `registrations` **deben ser diferentes**, por ejemplo **registration`-ik`.yaml**, **NO deben tener el mismo nombre**.
```bash
cp registration.yaml /var/data/dominio_cliente.com/synapse/registration-mapi.yaml
```

- Registrar el appservice en el `homeserver.yaml`:
```bash
vim /var/data/dominio_cliente.com/synapse/homeserver.yaml
```
- Buscar la sección `app_service_config_files`, si está comentada, des comentarla.
- Agregan el registration en la lista de appservices:
```bash
app_service_config_files:
  - /data/registration-ik.yaml
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