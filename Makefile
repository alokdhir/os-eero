PLUGIN_NAME=		eero
PLUGIN_VERSION=		1.1
PLUGIN_DEPENDS=		py${PLUGIN_PYTHON}-requests py${PLUGIN_PYTHON}-sqlite3
PLUGIN_COMMENT=		eero mesh Wi-Fi status: units, clients and network settings
PLUGIN_MAINTAINER=	alok@dhir.net
PLUGIN_WWW=		https://github.com/alokdhir/os-eero

.include "../../Mk/plugins.mk"
