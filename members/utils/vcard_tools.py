from io import BytesIO

import qrcode


def _escape_vcard_text(value):
    """Escape a vCard 3.0 text value, including embedded line breaks."""
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def generate_vcard(member, include_contact=True, contact_visibility=None):
    """Return a vCard string filtered by per-field contact visibility."""
    visibility = contact_visibility or {
        "email": include_contact,
        "phone": include_contact,
        "address": include_contact,
    }
    vcard_lines = ["BEGIN:VCARD", "VERSION:3.0"]
    vcard_lines.append(
        f"N:{_escape_vcard_text(member.last_name)};"
        f"{_escape_vcard_text(member.first_name)};;;"
    )
    vcard_lines.append(
        f"FN:{_escape_vcard_text(member.first_name)} "
        f"{_escape_vcard_text(member.last_name)}"
    )

    if any(visibility.values()):
        if visibility["email"] and member.email:
            vcard_lines.append(
                f"EMAIL;TYPE=INTERNET,HOME:{_escape_vcard_text(member.email)}"
            )
        if visibility["phone"] and member.phone:
            vcard_lines.append(
                f"TEL;TYPE=home,voice:{_escape_vcard_text(member.phone)}"
            )
        if visibility["phone"] and member.mobile_phone:
            vcard_lines.append(
                f"TEL;TYPE=cell,voice:{_escape_vcard_text(member.mobile_phone)}"
            )
        if member.glider_rating:
            vcard_lines.append(
                f"X-GLIDER-RATING:{_escape_vcard_text(member.glider_rating)}"
            )
        if visibility["address"]:
            address_components = (
                "",
                "",
                member.address,
                member.city,
                member.state_code or member.state_freeform,
                member.zip_code,
                member.country,
            )
            vcard_lines.append(
                "ADR;TYPE=HOME:"
                + ";".join(_escape_vcard_text(value) for value in address_components)
            )
    else:
        vcard_lines.append("NOTE: Contact information redacted")

    vcard_lines.append("END:VCARD")
    return "\r\n".join(vcard_lines) + "\r\n"


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
