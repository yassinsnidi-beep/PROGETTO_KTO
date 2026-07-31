import os
import sys
import time
import json
import requests
import pandas as pd

def parse_user(user):
    record = {
        'ID': user.get('id'),
        'Nome': user.get('firstName', '').strip() if user.get('firstName') else '',
        'Cognome': user.get('lastName', '').strip() if user.get('lastName') else '',
        'Email': user.get('email'),
        'Willing to Help': 'Sì' if user.get('isWillingToHelp') else 'No',
        'Foto URL': user.get('photoUrl'),
        'Stato': user.get('status'),
        'Badges': ", ".join([b.get('name') for b in user.get('badges') or [] if b.get('name')])
    }
    
    translations = user.get('categoryFieldItemTranslations') or {}
    
    # Estrae fino a 3 titoli di studio (Laurea, Laurea Magistrale, ecc.)
    majors = translations.get('majorFieldsSection') or []
    for i in range(3):
        prefix = f'Studio {i+1} - '
        if i < len(majors):
            deg = majors[i]
            record[prefix + 'Tipo'] = deg[0] if len(deg) > 0 else None
            record[prefix + 'Corso'] = deg[1] if len(deg) > 1 else None
            record[prefix + 'Dipartimento'] = deg[2] if len(deg) > 2 else None
            record[prefix + 'Anno'] = deg[3] if len(deg) > 3 else None
            record[prefix + 'Sede'] = deg[4] if len(deg) > 4 else None
        else:
            record[prefix + 'Tipo'] = None
            record[prefix + 'Corso'] = None
            record[prefix + 'Dipartimento'] = None
            record[prefix + 'Anno'] = None
            record[prefix + 'Sede'] = None
            
    # Estrae fino a 3 esperienze lavorative
    jobs = translations.get('professionalFieldsSection') or []
    for i in range(3):
        prefix = f'Lavoro {i+1} - '
        if i < len(jobs):
            job = jobs[i]
            record[prefix + 'Azienda'] = job[0] if len(job) > 0 else None
            record[prefix + 'Ruolo'] = job[1] if len(job) > 1 else None
        else:
            record[prefix + 'Azienda'] = None
            record[prefix + 'Ruolo'] = None
            
    return record

def main():
    print("=" * 60)
    print("        UNIBO ALUMNI DIRECTORY SCRAPER (BROWSERLESS)")
    print("=" * 60)
    
    url = 'https://api.ng.prod.europe-west1.manual.graduway.com/Directory/Search'
    
    # Utilizziamo i cookie ed header copiati dall'utente
    headers = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'en,it-IT;q=0.9,it;q=0.8,en-US;q=0.7',
        'authorization': 'bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJodHRwOi8vc2NoZW1hcy54bWxzb2FwLm9yZy93cy8yMDA1LzA1L2lkZW50aXR5L2NsYWltcy9uYW1lIjoieWFzc2luLnNuaWRpQGdtYWlsLmNvbSIsImh0dHA6Ly9zY2hlbWFzLnhtbHNvYXAub3JnL3dzLzIwMDUvMDUvaWRlbnRpdHkvY2xhaW1zL2VtYWlsYWRkcmVzcyI6Inlhc3Npbi5zbmlkaUBnbWFpbC5jb20iLCJodHRwOi8vc2NoZW1hcy54bWxzb2FwLm9yZy93cy8yMDA1LzA1L2lkZW50aXR5L2NsYWltcy9zaWQiOiI3OTQwNjgiLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL3JvbGUiOiJVc2VyIiwiZXhwIjoxNzg3OTcyOTkzLCJpc3MiOiJhcGlVc2VyIiwiYXVkIjoiYXBpQXVkaWVuY2UifQ.rW3JaZtSC7WnxqcIWnxYPH-zDNE46n-4m1l7BX1QS6o',
        'content-type': 'application/json',
        'horizontalid': '50153',
        'horizontalname': 'alumniunibo',
        'origin': 'https://alumni.unibo.it',
        'referer': 'https://alumni.unibo.it/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'
    }
    
    # Lasciamo freeText vuoto per scaricare tutti i profili
    payload_template = {
        "sortType": 1,
        "freeText": "",
        "displayLostAlumni": False,
        "companyIds": [],
        "paginationFilter": {
            "perPage": 20,
            "pageNumber": 1
        },
        "totalCount": 0,
        "coordinates": None,
        "bounds": None
    }
    
    output_file = "alumni_unibo.xlsx"
    all_records = []
    
    print("[1] Verifica della connessione ed estrazione del totale dei profili...")
    try:
        response = requests.post(url, headers=headers, json=payload_template)
        if response.status_code != 200:
            print(f"[-] Errore iniziale API: HTTP {response.status_code}")
            print(response.text)
            sys.exit(1)
            
        data = response.json()
        total_count = data.get('content', {}).get('data', {}).get('totalCount', 0)
        print(f"[+] Connessione stabilita con successo!")
        print(f"[+] Totale profili da scaricare: {total_count}")
    except Exception as e:
        print(f"[-] Impossibile contattare l'API: {e}")
        sys.exit(1)
        
    print("-" * 60)
    print("Avvio del download dei profili (20 per pagina).")
    print("Puoi interrompere in qualsiasi momento con CTRL+C e i dati parziali verranno salvati.")
    print("-" * 60)
    
    page = 1
    consecutive_errors = 0
    max_errors = 5
    
    try:
        while True:
            # Crea il payload specifico per questa pagina
            payload = payload_template.copy()
            payload["paginationFilter"] = {
                "perPage": 20,
                "pageNumber": page
            }
            
            print(f" -> Richiesta pagina {page}... ", end="", flush=True)
            
            res = requests.post(url, headers=headers, json=payload)
            if res.status_code != 200:
                print(f"ERRORE HTTP {res.status_code}")
                consecutive_errors += 1
                if consecutive_errors >= max_errors:
                    print("[-] Troppi errori consecutivi. Interruzione dello scraping.")
                    break
                time.sleep(5)
                continue
                
            consecutive_errors = 0
            res_data = res.json()
            users = res_data.get('content', {}).get('data', {}).get('directoryUsers', [])
            
            if not users:
                print("Fine dati raggiunta (pagina vuota).")
                break
                
            for u in users:
                parsed = parse_user(u)
                all_records.append(parsed)
                
            print(f"scaricati {len(users)} profili. (Totale accumulato: {len(all_records)} / {total_count})", flush=True)
            
            # Salvataggio periodico di sicurezza ogni 25 pagine
            if page % 25 == 0:
                print(f"   [Sicurezza] Salvataggio parziale di {len(all_records)} profili...", end="", flush=True)
                df = pd.DataFrame(all_records)
                df.to_excel(output_file, index=False)
                print(" fatto.", flush=True)
                
            page += 1
            # Pausa di cortesia per evitare rate limiting
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\n\n[!] Scraping interrotto dall'utente via tastiera (CTRL+C).")
        
    except Exception as e:
        print(f"\n[-] Si è verificato un errore durante lo scraping: {e}")
        
    if all_records:
        print(f"\n[+] Salvataggio finale di {len(all_records)} contatti in corso...")
        df = pd.DataFrame(all_records)
        df.to_excel(output_file, index=False)
        print(f"[+] Successo! Dati salvati in: {os.path.abspath(output_file)}")
        print(f"    Colonne salvate: {len(df.columns)}")
        print(f"    Righe totali: {len(df)}")
    else:
        print("\n[-] Nessun dato estratto, file Excel non creato.")

if __name__ == "__main__":
    main()
