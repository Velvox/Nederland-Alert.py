# Nederland-Alert.py
An unofficial open-source Discord bot that uses Dutch government API's to forward governement or Police issued notofication to Discord, in python.

### [Add the bot to your server or account](https://discord.com/oauth2/authorize?client_id=1325457566834364557)

## Required configuration
`.env` the environment file is critical and should contain the following.

```r
# Bot settings
NL_ALERT_IMAGE_URL = ""
# Bot configuration
BOT_TOKEN = ''
POLITIE_V5_API_VERMIST = "https://api.politie.nl/v5/vermist"
AMBER_ALERT_API = "https://services.burgernet.nl/landactiehost/api/v1/alerts"
NL_ALERT_API = "https://api.public-warning.app/api/v1/providers/nl-alert/alerts"
# MySQL configuration
MYSQLUSER = ''
MYSQLPASSOWRD = ''
MYSQLDATABASE = ''
MYSQLHOST = ''
MYSQLPORT = ''
MYSQLCACERTPATH = ''
```

The code expects a MySQL database with a TLS secured connection, if you run this localy you may want to remove or comment out in the .env file `MYSQLCACERTPATH` and remove the python code bellow.
```py
    'ssl': {
        'ca': f'{MYSQLCACERTPATH}',
    }
```

I will not write a complete setup guide because I do not intent that everyone is going run this bot for them selves. I posted this out of transparency. [Click here to invite the application to your Discord server or add it to your 'personal' applications](https://discord.com/oauth2/authorize?client_id=1325457566834364557). \
Or check our [Discovery listing](https://discord.com/discovery/applications/1325457566834364557).
