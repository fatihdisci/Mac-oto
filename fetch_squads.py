import requests, json, time, sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

API_KEY = 'd8551a9e53f80f770e4377d616b425cc'
BASE = 'https://v3.football.api-sports.io'
HDR = {'x-apisports-key': API_KEY}

session = requests.Session()
api_map = json.loads(open('data/api_football_teams.json', encoding='utf-8').read())
name_to_id = api_map['name_to_id']

MANUAL = {
    # Premier League
    'Arsenal': 42, 'Chelsea': 49, 'Aston Villa': 66, 'Liverpool FC': 40,
    'Manchester City FC': 50, 'Manchester United FC': 33, 'Tottenham Hotspur FC': 47,
    'Newcastle United FC': 34, 'Brentford': 55, 'Crystal Palace': 52,
    'Everton': 45, 'Fulham': 36, 'Burnley': 44, 'Wolves': 39,
    'Brighton & Hove Albion FC': 51, 'West Ham United FC': 48,
    'Leeds United FC': 63, 'Nottingham Forest FC': 65, 'AFC Bournemouth': 35,
    'Sunderland AFC': 60,
    # Bundesliga
    '1. FC Heidenheim 1846': 10267, '1. FC Köln': 192, '1. FC Union Berlin': 182,
    '1. FSV Mainz 05': 164, 'Bayer 04 Leverkusen': 168, 'Borussia Dortmund': 165,
    'Borussia Mönchengladbach': 163, 'Eintracht Frankfurt': 169,
    'FC Augsburg': 170, 'FC Bayern München': 157, 'FC St. Pauli 1910': 186,
    'Freiburg': 160, 'Hamburger SV': 172, 'RB Leipzig': 173,
    'SV Werder Bremen': 162, 'TSG 1899 Hoffenheim': 167,
    'VfB Stuttgart': 172, 'VfL Wolfsburg': 161,
    # La Liga
    'Athletic Club': 531, 'Atlético Madrid': 530, 'Barcelona': 529,
    'CA Osasuna': 727, 'Deportivo Alavés': 542, 'Elche': 542,
    'Espanyol': 538, 'Getafe': 546, 'Girona': 547, 'Levante': 724,
    'Rayo Vallecano de Madrid': 728, 'RC Celta de Vigo': 532, 'RCD Mallorca': 798,
    'Real Betis Balompié': 543, 'Real Madrid CF': 541, 'Real Oviedo': 726,
    'Real Sociedad de Fútbol': 548, 'Sevilla FC': 536, 'Valencia CF': 532,
    'Villarreal CF': 533,
    # Serie A
    'AC Milan': 489, 'AC Pisa 1909': 487, 'ACF Fiorentina': 502,
    'AS Roma': 497, 'Atalanta': 499, 'Bologna': 500, 'Cagliari': 490,
    'Como': 715, 'Cremonese': 512, 'FC Internazionale Milano': 505,
    'Genoa': 495, 'Hellas Verona FC': 504, 'Juventus FC': 496,
    'Parma Calcio 1913': 508, 'SS Lazio': 492, 'SSC Napoli': 492,
    'Torino FC': 503, 'Udinese Calcio': 494, 'US Lecce': 867, 'US Sassuolo Calcio': 509,
    # Ligue 1
    'AJ Auxerre': 108, 'Angers': 77, 'AS Monaco FC': 91, 'Brest': 115,
    'FC Lorient': 78, 'FC Metz': 112, 'FC Nantes': 83, 'Le Havre': 511,
    'Lens': 116, 'Lille': 79, 'Lyon': 80, 'Marseille': 81, 'OGC Nice': 84,
    'Paris FC': 1095, 'Paris Saint-Germain FC': 85, 'RC Strasbourg Alsace': 95,
    'Rennes': 111, 'Toulouse FC': 96,
    # Eredivisie
    'AFC Ajax': 194, 'AZ Alkmaar': 197, 'Excelsior': 217,
    'FC Groningen': 204, "FC Twente '65": 415, 'FC Utrecht': 418,
    'FC Volendam': 421, 'Feyenoord': 198, 'Fortuna Sittard': 423,
    'Go Ahead Eagles': 410, 'Heerenveen': 210, 'Heracles Almelo': 206,
    'NAC Breda': 203, 'NEC': 409, 'PEC Zwolle': 411, 'PSV': 199,
    'Sparta Rotterdam': 426, 'Telstar 1963': 427,
    # Super Lig
    'Alanyaspor': 4753, 'Antalyaspor': 218, 'Basaksehir': 611,
    'Beşiktaş': 215, 'Eyüpspor': 10025, 'Fatih Karagümrük': 10026,
    'Fenerbahçe': 214, 'Galatasaray': 213, 'Gaziantep': 2282,
    'Gençlerbirliği': 609, 'Göztepe': 10020, 'Kasimpasa': 608,
    'Kayserispor': 1001, 'Kocaelispor': 10027, 'Konyaspor': 607,
    'Rizespor': 1007, 'Samsunspor': 3603, 'Trabzonspor': 998,
    # CL/EL extra
    'Bodø/Glimt': 327, 'Club Brugge': 569, 'FC Copenhagen': 400,
    'Olympiacos': 611, 'Sporting Clube de Portugal': 228,
    'Crvena Zvezda': 1365, 'Dinamo Zagreb': 620,
    'Ferencvaros': 651, 'FC Midtjylland': 371, 'FC Porto': 212,
    'Genk': 472, 'Maccabi Tel Aviv': 635, 'Malmo': 375,
    'Panathinaikos': 617, 'Paok': 619, 'Rangers': 257, 'Celtic': 247,
    'Red Bull Salzburg': 571, 'Slavia Praha': 560, 'Sturm Graz': 1920,
    'Viktoria Plzen': 561, 'Young Boys': 562, 'Braga': 217,
    'Benfica': 211, 'Basel': 571,
    # National teams
    'Algeria': 4, 'Argentina': 6, 'Australia': 25, 'Austria': 26,
    'Belgium': 1, 'Brazil': 24, 'Canada': 101, 'Colombia': 11,
    'Croatia': 3, 'Czech Republic': 7, 'Ecuador': 65, 'Egypt': 23,
    'England': 10, 'France': 2, 'Germany': 25, 'Ghana': 60,
    'Iran': 39, 'Iraq': 37, 'Japan': 28, 'Mexico': 16,
    'Morocco': 32, 'New Zealand': 57, 'Norway': 19, 'Panama': 107,
    'Paraguay': 9, 'Portugal': 27, 'Qatar': 113, 'Saudi Arabia': 36,
    'Scotland': 8, 'Senegal': 77, 'South Africa': 29, 'South Korea': 35,
    'Spain': 9, 'Sweden': 20, 'Switzerland': 15, 'Tunisia': 27,
    'Turkey': 21, 'Uruguay': 7, 'USA': 13, 'Uzbekistan': 94,
}

teams_dir = 'data/teams'
all_teams = []
for fname in sorted(os.listdir(teams_dir)):
    if not fname.endswith('.json'):
        continue
    d = json.loads(open(f'{teams_dir}/{fname}', encoding='utf-8').read())
    for t in d.get('teams', []):
        all_teams.append({'key': t['team_id'], 'name': t['name'], 'league': t['league_slug']})

api_id_to_info = {}
unmatched_teams = []

for t in all_teams:
    api_id = name_to_id.get(t['name']) or MANUAL.get(t['name'])
    if api_id:
        if api_id not in api_id_to_info:
            api_id_to_info[api_id] = {'keys': [], 'name': t['name']}
        api_id_to_info[api_id]['keys'].append(t['key'])
    else:
        unmatched_teams.append(t)

print(f'Benzersiz API takim: {len(api_id_to_info)}')
print(f'Eslesmeyenler ({len(unmatched_teams)}):')
for t in unmatched_teams:
    print(f'  - {t["name"]} ({t["league"]})')

r = session.get(f'{BASE}/status', headers=HDR, timeout=15)
req_info = r.json().get('response', {}).get('requests', {})
used = int(req_info.get('current', 10))
limit = int(req_info.get('limit_day', 100))
remaining = limit - used
print(f'\nKota: {used}/{limit} - Kalan: {remaining} istek')

players_file = 'data/players.json'
if os.path.exists(players_file):
    existing = json.loads(open(players_file, encoding='utf-8').read())
    players_map = existing.get('players', {})
else:
    players_map = {}

fetched = 0
skipped = 0
errors = 0
budget = remaining - 1

for api_id, info in api_id_to_info.items():
    if fetched >= budget:
        print(f'\nGunluk kota doldu. Kalan: {len(api_id_to_info) - fetched - skipped} takim yarin cekilecek.')
        break

    all_filled = all(
        isinstance(players_map.get(k), dict) and players_map[k].get('players')
        for k in info['keys']
    )
    if all_filled:
        skipped += 1
        continue

    try:
        r = session.get(f'{BASE}/players/squads', headers=HDR,
                        params={'team': api_id}, timeout=20)
        data = r.json()
        response = data.get('response', [])
        players = []
        if response:
            squad = response[0].get('players', [])
            players = [p['name'] for p in squad if p.get('name')]

        for key in info['keys']:
            players_map[key] = {'name': info['name'], 'players': players}

        fetched += 1
        print(f'[{fetched}] {info["name"]}: {len(players)} oyuncu', flush=True)

        if fetched % 10 == 0:
            out = {'team_count': len(players_map), 'players': players_map}
            open(players_file, 'w', encoding='utf-8').write(
                json.dumps(out, ensure_ascii=False, indent=2))

        time.sleep(1.3)

    except Exception as e:
        print(f'  HATA {info["name"]}: {e}')
        errors += 1
        time.sleep(2)

out = {'team_count': len(players_map), 'players': players_map}
open(players_file, 'w', encoding='utf-8').write(json.dumps(out, ensure_ascii=False, indent=2))

filled = sum(1 for v in players_map.values() if isinstance(v, dict) and v.get('players'))
print(f'\n=== SONUC ===')
print(f'Cekilen   : {fetched}')
print(f'Atlanan   : {skipped}')
print(f'Hata      : {errors}')
print(f'Toplam dolu: {filled}/{len(players_map)}')
print(f'Kaydedildi: {players_file}')
