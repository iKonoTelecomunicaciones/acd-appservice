# v0.2.6 (2023-01-31)
- Corrección de errores cuando el destino está establecido
- Corrección de errores en el proceso de destino
- Corrección de errores cuando los invitados son una cadena vacía
- Renombrar métodos para obtener membresías serializadas
- Cambios sugeridos en la estructura de los datos a devolver
- Refactorización para el uso de portal y cola en algunas partes del código
- Endpoint de miembros modificado para devolver el estado de todos los agentes
- Corrección cuando se crea la habitación y no se invita a menubot
- Corrección de errores cuando el agente deja la cola
- Agregada nueva acción de cola que agrega habitaciones previamente creadas
- Agregado método para obtener el tema de la habitación
- Agregado soporte para la conexión con el puente de Facebook
- Agregado ejemplos en la documentación de inicio de sesión y desafío
- Corrección de errores en la consulta de la base de datos de portal
- Cambiar el permiso de ejecución del comando de cola
- Responder el error cuando el comando falla
- Agregado nuevo endpoint update_members
- Agregado displayname en la respuesta de membresía de usuario
- Corrección de errores en la lista de membresías de la cola
- Mejorar el nombre de las funciones para consultar la base de datos
- Corrección de errores en el comando de cola
- Corrección de errores en los endpoints de información y lista de cola
- Eliminar estado de portal no utilizado y corrección de ortografía


# v0.2.5 (2023-01-03)
- Agregado de todas las operaciones CRUD para el comando de colas.
- Renombrado de la clase Room a MatrixRoom.
- Adición y eliminación de agentes a una cola.
- Expansión de la operación del procesador de comandos.
- Mejora de los logs en las operaciones de agentes.
- Obtención de la versión desde Git.
- Corrección de errores en las operaciones de agentes.
- Corrección de la falla en la intención de cola.
- Solución de fechas en las operaciones de agentes.
- Corrección del bug en el estado de pausa de los agentes.
- Interfaz para las colas.
- Endpoint para obtener el estado de pausa de los agentes.
- Corrección de errores en el endpoint de miembros.
- Adición del nombre de la sala en la respuesta JSON en el comando de miembros.
- Endpoint para obtener los miembros del usuario.
- Corrección de bugs en la resolución del identificador del muñeco.

# v0.2.4.2 (2023-01-25)
- Se cambió el método para eliminar room_id
- Se corrigió el problema al crear la sala y no invitar a menubot.

# v0.2.4.1 (2022-12-13)
- Corregido error mautrix python caché

# v0.2.4 (2022-12-07)
- Refactorización del procesador de comandos con una nueva estructura de documentación.
- Añadido de un comando de pausa de miembro.
- Ajuste en la base de datos para agregado un campo de descripción a la tabla de colas y utilizarlo en el comando de cola.
- Adición de operaciones de agente, incluyendo inicio de sesión y cierre de sesión.
- Adición de un comando para crear colas de agentes desde el ACD.
- Envío de mensajes sin formato a puentes que no admiten mensajes con formato.
- Añadido de sugerencias.
- Corrección de errores en el comando de creación.
- Adición de pruebas para los comandos de miembro y pausa de miembro.
- Cambio en el tipo de datos de fecha y hora en la tabla de membresía de cola.

# v0.2.3 (2022-11-15)
- Se resolvió un bug relacionado con el control de la habitación al distribuir el chat cuando el id de la habitación de la campaña es nulo.

# v0.2.2 (2022-11-03)
- Se arregló un error relacionado con el comando de transferencia, cuando el identificador de la sala (room_id) de la campaña no estaba disponible para el ACD principal.
- Se corrigió la función get_bridges_status para saltarse la validación de estado del puente gupshup.
- Se agregó un endpoint en la API para el comando ACD.
- Se realizaron mejoras en la documentación del endpoint logout.
- Se realizaron refactorizaciones en get_bridges_status, ProvisionBridge y se creó el endpoint logout.

# v0.2.0 (2022-10-18)
- Se resolvió un bug reportado en 18/10/2022
- Se agregó un endpoint para obtener el estado de los canales
- Se corrigió un error en la función transfer_user
- Se agregó un argumento "force" a la función transfer_user para obligar a la transferencia de usuario
- Se agregó una nueva función para crear comandos y se refactorizó el módulo web para tener endpoint separados
- Se actualizó el archivo README.md
- Se agregadoon funcionalidades para la gestión de salas
- Se agregó un script para el equipo de desarrollo
- Se cambió la URL del servicio de Gupshup a la URL de instalación por defecto del puente
- Se actualizaron los procesos de CI/CD
- Se eliminó la necesidad de enviar un correo electrónico al crear un usuario de muñeca
- Se ignoró el directorio "dev" y se eliminó
- Se agregadoon sugerencias y se corrigió un error en el archivo de configuración config.py relacionado con el parámetro leave_or_kick
- Se parametrizó el comando para expulsar o abandonar un usuario.


# v0.1.9 (2022-09-15)
- El bot principal de ACD distribuye chats en salas grupales
- Actualización de dependencias y eliminación de imports no utilizados
- Corrección de un bug al registrar la aplicación de Gupshup
- Movimiento del menú fuera de línea a una ubicación mejor
- Cambio de la sesión de httpclient a la sesión de puppet
- Refactorización de CommandEvent
- Actualización de docker-compose y .gitignore
- Eliminación del campo de puente en la solicitud de resolución de una sala
- Corrección de un error de Diana
- Adición del nombre del agente en el mensaje de transferencia
- Documentación agregada para el endpoint create_user
- Adición de una función donde los usuarios no son expulsados sino que salen por su cuenta.


# v0.1.8 (2022-08-31)
- ➕ ADD FEATURE: Ahora puedes enviar mensajes vía gupshup con este endpoint `/v1/gupshup/send_message`
- ➕ ADD FEATURE: Ahora puedes crear líneas con gupshup con este endpoint `/v1/gupshup/register`
- ➕ ADD FEATURE: Este ACD soporta el bridge de gupshup
- 🔃 CODE REFACTORING: Cambios en los endpoints
    - `/v1/whatsapp/send_message` -> `/v1/mautrix/send_message`
    - `/v1/whatsapp/link_phone` -> `/v1/mautrix/link_phone`
    - `/v1/whatsapp/ws_link_phone` -> `/v1/mautrix/ws_link_phone`
- 🔃 CODE REFACTORING: El comando pm fue modificado para que funcione a la par de mautrix y gupshup

# v0.1.7 (2022-08-24)

- 🐛 BUG FIX: El evento join llegaba antes del invite, las salas no inicializaban bien
- 🐛 BUG FIX: La puppet_password se actualizaba sola al reiniciar el servicio
- ➖ SUB CODE: Se elimina código repetido

# v0.1.6 (2022-22-08)

- 🐛 BUG FIX: Bug relacionado con joined_message
- ➕ ADD FEATURE: Ahora se generar puppet password automaticamente
...

# v0.0.0 (2022-06-06)

Initial tagged release.
