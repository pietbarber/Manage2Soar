from django import template

register = template.Library()


@register.filter
def split_lines(value):
    """Split text by newlines and return non-empty lines."""
    if not value:
        return []
    return [line.strip() for line in value.split('\n') if line.strip()]


@register.filter
def format_address(site_config):
    """Format a complete address from SiteConfiguration fields."""
    if not site_config:
        return ["Contact us for location information"]

    address_parts = []

    if site_config.club_address_line1:
        address_parts.append(site_config.club_address_line1)

        if site_config.club_address_line2:
            address_parts.append(site_config.club_address_line2)

        # City, State ZIP
        city_state_zip = []
        if site_config.club_city:
            city_state_zip.append(site_config.club_city)
        if site_config.club_state:
            city_state_zip.append(site_config.club_state)

        city_line = ", ".join(city_state_zip)
        if site_config.club_zip_code:
            city_line = f"{city_line} {site_config.club_zip_code}".strip()

        if city_line:
            address_parts.append(city_line)

        # Country (if not USA)
        if site_config.club_country and site_config.club_country.upper() != 'USA':
            address_parts.append(site_config.club_country)
    else:
        return ["Contact us for location information"]

    return address_parts


@register.filter
def google_maps_url(site_config):
    """Generate a Google Maps URL from SiteConfiguration address fields."""
    if not site_config or not site_config.club_address_line1:
        return None

    # Build complete address string for Google Maps
    address_parts = []

    if site_config.club_address_line1:
        address_parts.append(site_config.club_address_line1)
    if site_config.club_address_line2:
        address_parts.append(site_config.club_address_line2)
    if site_config.club_city:
        address_parts.append(site_config.club_city)
    if site_config.club_state:
        address_parts.append(site_config.club_state)
    if site_config.club_zip_code:
        address_parts.append(site_config.club_zip_code)
    if site_config.club_country and site_config.club_country.upper() != 'USA':
        address_parts.append(site_config.club_country)

    # Join address parts and URL encode
    full_address = ", ".join(address_parts)

    # Use urllib.parse to properly encode the address
    from urllib.parse import quote_plus
    encoded_address = quote_plus(full_address)

    return f"https://www.google.com/maps/search/?api=1&query={encoded_address}"
