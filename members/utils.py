import qrcode
from io import BytesIO
from django.core.files.base import ContentFile

def generate_vcard_qr(member):
    vcard = f"""BEGIN:VCARD
VERSION:3.0
N:{member.last_name};{member.first_name}
FN:{member.first_name} {member.last_name}
EMAIL:{member.email}
"""
    if member.phone:
        vcard += f"TEL;TYPE=home,voice:{member.phone}\n"
    if member.mobile_phone:
        vcard += f"TEL;TYPE=cell,voice:{member.mobile_phone}\n"
    if member.glider_rating:
        vcard += f"X-GLIDER-RATING:{member.glider_rating}\n"
    vcard += f"""ADR:;;{member.address};{member.city};{member.state};{member.zip_code}
END:VCARD"""
    qr = qrcode.make(vcard)
    buffer = BytesIO()
    qr.save(buffer, format='PNG')
    return buffer.getvalue()
