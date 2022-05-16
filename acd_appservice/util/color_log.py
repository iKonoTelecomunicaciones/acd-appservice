from mautrix.util.logging.color import MXID_COLOR, PREFIX, RESET
from mautrix.util.logging.color import ColorFormatter as BaseColorFormatter

ACD_COLOR = PREFIX + "32m"  # green


class ColorFormatter(BaseColorFormatter):
    def _color_name(self, module: str) -> str:
        if module.startswith("mau"):
            return ACD_COLOR + module + RESET
        elif module.startswith("mau.acd_appservice"):
            mau, acd, subtype, user_id = module.split(".", 3)
            return (
                ACD_COLOR + f"{mau}.{acd}.{subtype}" + RESET + "." + MXID_COLOR + user_id + RESET
            )
        return super()._color_name(module)
