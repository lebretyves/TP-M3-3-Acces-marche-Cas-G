"""Outil réservé au poste de démonstration, aucune route web équivalente."""
import json
import time
import pyotp
from .database import ROOT


if __name__=='__main__':
    accounts=json.loads((ROOT/'.runtime/comptes_locaux.json').read_text(encoding='utf-8'))
    print('Codes de test locaux - ne pas diffuser. Chaque code ne peut servir qu’une fois.')
    print('Validité restante :',30-int(time.time())%30,'secondes. Relancer pour renouveler.')
    for a in accounts:
        print(a['username'].ljust(20),pyotp.TOTP(a['otp_secret']).now())
