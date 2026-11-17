from pathlib import Path

import yaml

PLAYBOOK = Path(__file__).with_name("gcp-mail-server.yml")


def test_postfix_tag_includes_milter_dependencies_and_inbound_sync_guard():
    plays = yaml.safe_load(PLAYBOOK.read_text())
    configure = next(play for play in plays if play["name"] == "Configure Mail Server")
    roles = {role["role"]: role for role in configure["roles"]}

    assert "postfix" in roles["opendkim"]["tags"]
    assert "postfix" in roles["rspamd"]["tags"]
    assert roles["m2s-mail-sync"]["when"] == (
        "gcp_enable_inbound_smtp | default(true) | bool"
    )


def test_dkim_and_dns_output_uses_resolved_opendkim_domains():
    playbook = PLAYBOOK.read_text()

    assert 'loop: "{{ opendkim_domains }}"' in playbook
    assert "{% for domain in opendkim_domains %}" in playbook
    assert "item.prefix" not in playbook

    for filename in ("mail-server.yml", "single-host.yml"):
        content = PLAYBOOK.with_name(filename).read_text()
        assert "opendkim_domains" in content
        assert "opendkim_keys_dir" in content
        assert "club.prefix }}.{{ mail_domain" not in content
        assert "._domainkey.{{ mail_domain" not in content
