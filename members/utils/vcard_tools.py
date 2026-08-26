from io import BytesIO

import qrcode


def generate_vcard(member, include_contact=True, contact_visibility=None):
    """Return a vCard string filtered by per-field contact visibility."""
    visibility = contact_visibility or {
        "email": include_contact,
        "phone": include_contact,
        "address": include_contact,
    }
    vcard_lines = ["BEGIN:VCARD", "VERSION:3.0"]
    vcard_lines.append(f"N:{member.last_name};{member.first_name}")
    vcard_lines.append(f"FN:{member.first_name} {member.last_name}")

    if any(visibility.values()):
        if visibility["email"] and member.email:
            vcard_lines.append(f"EMAIL;TYPE=INTERNET,HOME:{member.email}")
        if visibility["phone"] and member.phone:
            vcard_lines.append(f"TEL;TYPE=home,voice:{member.phone}")
        if visibility["phone"] and member.mobile_phone:
            vcard_lines.append(f"TEL;TYPE=cell,voice:{member.mobile_phone}")
        if member.glider_rating:
            vcard_lines.append(f"X-GLIDER-RATING:{member.glider_rating}")
        if visibility["address"]:
            vcard_lines.append(
                f"ADR;TYPE=HOME:w:;;{member.address or ''};{member.city or ''};{member.state_code or ''}{member.state_freeform or ''};{member.zip_code or ''}"
            )
    else:
        vcard_lines.append("NOTE: Contact information redacted")

    vcard_lines.append("END:VCARD")
    return "\n".join(vcard_lines)


def generate_vcard_qr(member, include_contact=True, contact_visibility=None):
    """Generate a PNG vCard QR for a member.

    If include_contact is False, only include the minimal name fields and a
    NOTE that contact information is redacted. This prevents leaking emails,
    phone numbers, or postal addresses in the QR when a member has chosen to
    redact their contact details.
    """
    vcard = generate_vcard(member, include_contact, contact_visibility)

    qr = qrcode.make(vcard)
    buffer = BytesIO()
    # qrcode.make returns a PIL Image; call .save without kwarg name for compatibility
    qr.save(buffer, "PNG")
    return buffer.getvalue()
