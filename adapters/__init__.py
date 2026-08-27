"""Dedicated source adapters added in Funding Intelligence v0.3.

Each module keeps the source contract local.  Shared helpers in ``_common``
only handle safe HTML decoding, bounded card context and field inference; the
source-specific inclusion rules remain in the individual adapter classes.
"""

from .pari_opportunita import PariOpportunitaAdapter
from .dipendenze import DipendenzeAdapter
from .fami import FamiAdapter
from .pn_scuola import PnScuolaAdapter
from .fondazione_venezia import FondazioneVeneziaAdapter
from .intesa_beneficenza import IntesaBeneficenzaAdapter
from .compagnia_san_paolo import CompagniaSanPaoloAdapter
from .fondazione_cariplo import FondazioneCariploAdapter
from .fondazione_con_il_sud import FondazioneConIlSudAdapter
from .fondazione_crt import FondazioneCrtAdapter
from .fondazione_cr_firenze import FondazioneCrFirenzeAdapter
from .fondazione_crc import FondazioneCrcAdapter
from .fondazione_sardegna import FondazioneSardegnaAdapter
from .fondazione_friuli import FondazioneFriuliAdapter
from .ministero_lavoro_terzo_settore import MinisteroLavoroTerzoSettoreAdapter
from .aics import AicsAdapter
from .european_youth_foundation import EuropeanYouthFoundationAdapter
from .erasmus_inapp import ErasmusInappAdapter
from .fondazione_cariparma import FondazioneCariparmaAdapter
from .fondazione_modena import FondazioneModenaAdapter
from .fondazione_carisbo import FondazioneCarisboAdapter

__all__ = [
    "PariOpportunitaAdapter", "DipendenzeAdapter", "FamiAdapter", "PnScuolaAdapter",
    "FondazioneVeneziaAdapter", "IntesaBeneficenzaAdapter", "CompagniaSanPaoloAdapter",
    "FondazioneCariploAdapter", "FondazioneConIlSudAdapter", "FondazioneCrtAdapter",
    "FondazioneCrFirenzeAdapter", "FondazioneCrcAdapter", "FondazioneSardegnaAdapter",
    "FondazioneFriuliAdapter",
    "MinisteroLavoroTerzoSettoreAdapter", "AicsAdapter", "EuropeanYouthFoundationAdapter",
    "ErasmusInappAdapter", "FondazioneCariparmaAdapter", "FondazioneModenaAdapter", "FondazioneCarisboAdapter",
]
