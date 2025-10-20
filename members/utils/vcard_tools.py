from io import BytesIO

import qrcode


def generate_vcard_qr(member, include_contact=True):
    """Generate a PNG vCard QR for a member.

    If include_contact is False, only include the minimal name fields and a
    NOTE that contact information is redacted. This prevents leaking emails,
    phone numbers, or postal addresses in the QR when a member has chosen to
    redact their contact details.
    """
    vcard_lines = ["BEGIN:VCARD", "VERSION:3.0"]
    vcard_lines.append(f"N:{member.last_name};{member.first_name}")
    vcard_lines.append(f"FN:{member.first_name} {member.last_name}")

    if include_contact:
        if member.email:
            vcard_lines.append(f"EMAIL;TYPE=INTERNET,HOME:{member.email}")
        if member.phone:
            vcard_lines.append(f"TEL;TYPE=home,voice:{member.phone}")
        if member.mobile_phone:
            vcard_lines.append(f"TEL;TYPE=cell,voice:{member.mobile_phone}")
        if member.glider_rating:
            vcard_lines.append(f"X-GLIDER-RATING:{member.glider_rating}")
        # Address in a single ADR line (best-effort)
        adr = f"ADR;TYPE=HOME:w:;;{member.address or ''};{member.city or ''};{member.state_code or ''}{member.state_freeform or ''};{member.zip_code or ''}"
        vcard_lines.append(adr)
    else:
        vcard_lines.append("NOTE: Contact information redacted")

    vcard_lines.append("END:VCARD")
    vcard = "\n".join(vcard_lines)

    qr = qrcode.make(vcard)
    buffer = BytesIO()
    # qrcode.make returns a PIL Image; call .save without kwarg name for compatibility
    qr.save(buffer, "PNG")
    return buffer.getvalue()
