"""Explicit local operator display of synthetic-bank credentials; never run in CI."""
import hashlib
import argparse
from pathlib import Path
import pyotp

ROOT=Path(__file__).resolve().parents[1]
ACCOUNTS=('u-alice','c-lina','e-atelier','t-support','s-securite','s-approbateur')

def current_code(account):
    if account not in ACCOUNTS:raise ValueError('Compte de recette inconnu.')
    secret=ROOT/'.runtime/oidc-qa'/(account+'.otp')
    return pyotp.TOTP(secret.read_text().strip().replace(' ',''),digest=hashlib.sha256).now()


def main():
    print('SKELIVIA - ACCES CONFIDENTIELS AU BANC FICTIF LOCAL')
    print('Ne pas copier cette sortie dans Git, un rapport ou une capture partagee.')
    print('https://localhost:8443 - codes temporaires valables environ 30 secondes.\n')
    for account in ACCOUNTS:
        password=ROOT/'.runtime/infra/secrets'/('login_'+account)
        if not password.is_file():continue
        secret=ROOT/'.runtime/oidc-qa'/(account+'.otp')
        code=pyotp.TOTP(secret.read_text().strip().replace(' ',''),digest=hashlib.sha256).now() if secret.is_file() else 'Enrolement OTP requis dans Keycloak'
        print(account+'\nMot de passe : '+password.read_text().strip()+'\nCode temporaire : '+code+'\n')
    print('Les facteurs regroupes sur ce PC servent uniquement a la recette locale.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--code',choices=ACCOUNTS)
    args=parser.parse_args()
    if args.code:print(current_code(args.code))
    else:main()
