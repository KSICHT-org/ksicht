"""Consistent display formatting for Czech and Slovak participant phones."""


def normalize_phone_number(raw_phone):
    """Format recognized numbers without discarding unexpected input."""
    if not raw_phone:
        return ""
    phone = raw_phone.strip()
    compact = phone.replace(" ", "")
    if (
        compact.startswith(("+420", "+421"))
        and len(compact) == 13
        and compact[1:].isascii()
        and compact[1:].isdigit()
    ):
        return f"{compact[:4]} {compact[4:7]} {compact[7:10]} {compact[10:13]}"
    if len(compact) == 9 and compact.isascii() and compact.isdigit():
        return f"+420 {compact[:3]} {compact[3:6]} {compact[6:9]}"
    return phone
