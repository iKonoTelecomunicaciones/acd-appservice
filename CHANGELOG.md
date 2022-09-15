# v0.1.8 (2022-31-08)
- ➕ ADD FEATURE: Ahora puedes enviar mensajes vía gupshup con este endpoint `/v1/gupshup/send_message`
- ➕ ADD FEATURE: Ahora puedes crear líneas con gupshup con este endpoint `/v1/gupshup/register`
- ➕ ADD FEATURE: Este ACD soporta el bridge de gupshup
- 🔃 CODE REFACTORING: Cambios en los endpoints
    - `/v1/whatsapp/send_message` -> `/v1/mautrix/send_message`
    - `/v1/whatsapp/link_phone` -> `/v1/mautrix/link_phone`
    - `/v1/whatsapp/ws_link_phone` -> `/v1/mautrix/ws_link_phone`
- 🔃 CODE REFACTORING: El comando pm fue modificado para que funcione a la par de mautrix y gupshup

# v0.1.7 (2022-24-08)

- 🐛 BUG FIX: El evento join llegaba antes del invite, las salas no inicializaban bien
- 🐛 BUG FIX: La puppet_password se actualizaba sola al reiniciar el servicio
- ➖ SUB CODE: Se elimina código repetido

# v0.1.6 (2022-22-08)

- 🐛 BUG FIX: Bug relacionado con joined_message
- ➕ ADD FEATURE: Ahora se generar puppet password automaticamente
...

# v0.0.0 (2022-06-06)

Initial tagged release.
