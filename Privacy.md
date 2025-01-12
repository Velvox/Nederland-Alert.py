# Privacybeleid

Laatst bijgewerkt: 12/01/2025

### Over deze bot
Deze bot is een open-source project dat als doel heeft om waarschuwingsmeldingen, vermissingen en relevante informatie te aggregeren en te verspreiden via Discord. De bot maakt gebruik van openbare API's, waaronder maar niet beperkt tot:
- **Amber Alert API**: Voor meldingen van vermiste kinderen (in levens gevaar).
- **NL-Alert API**: Voor noodwaarschuwingen.
- **Politie V4 API**: Voor informatie over vermiste personen.

De bot is niet verbonden met of gesponsord door officiële instanties, waaronder de Nederlandse Overheid, Politie of Amber Alert-organisaties.

### Verzamelde gegevens
De bot verzamelt en verwerkt de volgende gegevens om zijn functies uit te voeren:
- **Discord-gebruiker-ID's**: Voor gebruikers die zich aanmelden om meldingen via directe berichten te ontvangen.
- **Guild- en kanaal-ID's**: Voor het versturen van meldingen naar specifieke kanalen binnen Discord-servers.
- **Waarschuwings- en meldinggegevens**: Informatie zoals titels, beschrijvingen en tijdstempels die via de API's worden opgehaald.

**Belangrijk**: De bot slaat geen gevoelige persoonlijke informatie op die niet nodig is voor het functioneren van de dienst.

### Doeleinden van gegevensverwerking
De verzamelde gegevens worden gebruikt voor:
1. Het versturen van meldingen naar geselecteerde Discord-kanalen of gebruikers.
2. Het controleren en filteren van dubbele meldingen om spam te voorkomen.
3. Het verbeteren van de betrouwbaarheid en functionaliteit van de bot.

### Hoe gegevens worden opgeslagen
De bot gebruikt een MySQL-database om bepaalde gegevens op te slaan, zoals:
- Gebruiker- en kanaal-ID's die toestemming hebben gegeven om meldingen te ontvangen.
- Waarschuwingsmeldingen die al zijn verzonden om duplicaten te voorkomen.

### Gegevensdeling met derden
De bot deelt geen gegevens met derden. Alle communicatie met externe API's gebeurt direct en volgens de richtlijnen van de API-aanbieders. Er wordt geen extra data buiten de functionaliteit van de bot gedeeld.

### Beveiliging
We hebben technische en organisatorische maatregelen geïmplementeerd om de gegevens die door de bot worden verwerkt te beschermen, waaronder:
- **Encryptie**: API-communicatie vindt plaats via HTTPS.
- **Beveiligde opslag**: Gegevens worden alleen opgeslagen in beveiligde databases met beperkte toegang.
- **Open source**: De broncode van de bot is beschikbaar voor transparantie en beveiligingsaudits.

### Rechten van gebruikers
Gebruikers hebben de volgende rechten met betrekking tot hun gegevens:
1. **Inzage**: U kunt verzoeken welke gegevens de bot over u bewaart.
2. **Correctie**: U kunt verzoeken om onjuiste gegevens te corrigeren.
3. **Verwijdering**: U kunt zich op elk moment uitschrijven voor meldingen, waarna uw gegevens worden verwijderd.

Verzoeken kunnen worden ingediend via de beheerders van de bot Velvox.
- **E-mail** support@velvox.net

### Contact
Voor vragen of meldingen met betrekking tot privacy of beveiliging, kunt u contact opnemen via de via e-mail met Velvox.
- **E-mail** support@velvox.net

**Disclaimer**: Dit project wordt onderhouden door de community en Velvox en biedt geen garantie voor tijdige meldingen of foutloze werking. Gebruik de bot op eigen risico.
