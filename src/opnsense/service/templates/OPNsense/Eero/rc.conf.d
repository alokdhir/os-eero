{% if not helpers.empty('OPNsense.Eero.general.enabled') %}
eero_enable="YES"
{% else %}
eero_enable="NO"
{% endif %}
