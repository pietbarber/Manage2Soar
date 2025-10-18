from io import BytesIO

import qrcode


def generate_vcard_qr(member):
    vcard = f"""BEGIN:VCARD
VERSION:3.0
N:{member.last_name};{member.first_name}
FN:{member.first_name} {member.last_name}
EMAIL;TYPE=INTERNET,HOME:{member.email}
"""
    if member.phone:
        vcard += f"TEL;TYPE=home,voice:{member.phone}\n"
    if member.mobile_phone:
        vcard += f"TEL;TYPE=cell,voice:{member.mobile_phone}\n"
    if member.glider_rating:
        vcard += f"X-GLIDER-RATING:{member.glider_rating}\n"
    adr_line = (
        (
            "ADRi;TYPE=HOME:w:;;{address};{city};{state}{freeform};{zip}\n"
        ).format(
            address=member.address,
            city=member.city,
            state=member.state_code,
            freeform=member.state_freeform or "",
            zip=member.zip_code,
        )
    )
    vcard += adr_line + "END:VCARD"
    qr = qrcode.make(vcard)
    buffer = BytesIO()
    qr.save(buffer, "PNG")
    return buffer.getvalue()
