# UFW Firewall Role

Configures UFW (Uncomplicated Firewall) with sensible defaults and flexible port configuration.

## Features

- Default deny incoming, allow outgoing policy
- Always allows SSH (configurable port)
- Flexible port configuration with source restrictions
- Optional UFW reset for clean state
- Displays final firewall status

## Requirements

- Ubuntu/Debian system
- `community.general` Ansible collection for UFW module

## Role Variables

### Default Policies

- `ufw_default_incoming_policy`: Default incoming policy (default: `deny`)
- `ufw_default_outgoing_policy`: Default outgoing policy (default: `allow`)

### SSH Access

- `ufw_allow_ssh`: Always allow SSH (default: `true`)
- `ufw_ssh_port`: SSH port to allow (default: `22`)

### Port Configuration

- `ufw_allow_ports`: List of ports to allow (default: `[]`)

Each item can be:
- Simple port number: `80`
- Port with protocol: `{ port: 443, proto: tcp }`
- Port with source restriction: `{ port: 5432, proto: tcp, src: "10.0.0.0/8" }`
- Port with comment: `{ port: 8000, proto: tcp, comment: "Django dev server" }`

### Control

- `ufw_enabled`: Enable UFW (default: `true`)
- `ufw_reset`: Reset UFW rules before applying (default: `false`, use with caution)

## Example Usage

### Basic Web Server

```yaml
- hosts: webservers
  roles:
    - role: ufw
      vars:
        ufw_allow_ports:
          - 80
          - 443
```

### Database Server

```yaml
- hosts: databases
  roles:
    - role: ufw
      vars:
        ufw_allow_ports:
          - port: 5432
            proto: tcp
            src: "10.0.0.0/8"
            comment: "PostgreSQL from private network"
```

### Mail Server

```yaml
- hosts: mailservers
  roles:
    - role: ufw
      vars:
        ufw_allow_ports:
          - { port: 25, proto: tcp, comment: "SMTP" }
          - { port: 587, proto: tcp, comment: "Submission" }
          - { port: 80, proto: tcp, comment: "HTTP for Let's Encrypt" }
```

### Multi-Service Server

```yaml
- hosts: app_servers
  roles:
    - role: ufw
      vars:
        ufw_ssh_port: 2222  # Custom SSH port
        ufw_allow_ports:
          - 80
          - 443
          - port: 5432
            proto: tcp
            src: "192.168.1.0/24"
```

## Dependencies

- `community.general` Ansible collection (for `community.general.ufw` module)

## License

Same as parent project

## Author

Manage2Soar Infrastructure Team
