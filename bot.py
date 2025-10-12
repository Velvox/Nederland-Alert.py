import pymysql # pyright: ignore[reportMissingModuleSource]
import discord # pyright: ignore[reportMissingImports]
from discord.ext import commands, tasks # pyright: ignore[reportMissingImports]
from datetime import datetime
import itertools
import requests
import re
import math
from dotenv import dotenv_values


intents = discord.Intents.default()
intents.message_content = False
intents.members = False

bot = commands.Bot(command_prefix=lambda bot, msg: [], intents=intents)

# DotEnv configuration
config = dotenv_values(".env")
MYSQLHOST           = config.get("MYSQLHOST")
MYSQLUSER           = config.get("MYSQLUSER")
MYSQLPASSOWRD       = config.get("MYSQLPASSOWRD")
MYSQLDATABASE       = config.get("MYSQLDATABASE")
MYSQLPORT           = int(config.get("MYSQLPORT", 3306)) # pyright: ignore[reportArgumentType]
MYSQLCACERTPATH     = config.get("MYSQLCACERTPATH")

BOT_TOKEN                 = config.get("BOT_TOKEN")
NL_ALERT_IMAGE_URL        = config.get("NL_ALERT_IMAGE_URL")
POLITIE_V5_API_VERMIST    = config.get("POLITIE_V5_API_VERMIST")
AMBER_ALERT_API           = config.get("AMBER_ALERT_API")
NL_ALERT_API              = config.get("NL_ALERT_API")



db_config = {
    'host': MYSQLHOST,  # Change this to your MySQL host
    'user': MYSQLUSER,  # Your MySQL username
    'password': MYSQLPASSOWRD,  # Your MySQL password
    'database': MYSQLDATABASE,  # Your database name
    'port': int(MYSQLPORT), # MySQL port
    'cursorclass': pymysql.cursors.DictCursor,
    'ssl': {
        'ca': f'{MYSQLCACERTPATH}',
    }
}

activities = itertools.cycle([
    discord.Activity(type=discord.ActivityType.watching, name="NL-Alerts"),
    discord.Activity(type=discord.ActivityType.watching, name="Amber Alerts"),
    discord.Activity(type=discord.ActivityType.playing, name="Politie V5 API")
])

@tasks.loop(seconds=5)
async def change_activity():
    current_activity = next(activities)
    await bot.change_presence(activity=current_activity)

@bot.event
async def on_ready():
    print(f'[INFO] Logged in as {bot.user}')
    change_activity.start() # pyright: ignore[reportFunctionMemberAccess]
    fetch_nl_alerts.start() # pyright: ignore[reportFunctionMemberAccess]
    fetch_amber_alerts.start() # pyright: ignore[reportFunctionMemberAccess]
    fetch_missing_persons.start() # pyright: ignore[reportFunctionMemberAccess] # V5 LOOP
    await bot.tree.sync()
    print('[INFO] Slash commands synchronized with Discord.')
    print(f'Bot started successfully')

# Zet ISO 8601 datum om naar Unix timestamp voor Discord
def iso_to_unix(iso_date):
    dt = datetime.strptime(iso_date, "%Y-%m-%dT%H:%M:%SZ")
    return int(dt.timestamp())

async def send_embed_to_all_users(bot, embed):
    connection = pymysql.connect(**db_config)
    cursor = connection.cursor()

    try:
        cursor.execute("SELECT user_id FROM discord_dm_users")
        user_ids = cursor.fetchall()

        for user_id in user_ids:
            user = await bot.fetch_user(user_id['user_id']) # pyright: ignore[reportArgumentType, reportCallIssue]
            await user.send(embed=embed)

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        cursor.close()
        connection.close()

### NL-ALERT BLOK
@tasks.loop(minutes=2)
async def fetch_nl_alerts():
    response = requests.get(NL_ALERT_API) # pyright: ignore[reportArgumentType]
    print(f"[INFO] Requested alerts with status code: {response.status_code}")

    try:
        json_response = response.json()
        alerts = json_response.get('data', [])

        if isinstance(alerts, list):
            for alert in alerts:
                alert_id = alert.get('id')
                title = alert.get('message', 'No Title')
                description = alert.get('type', 'No Description')  
                start_at_iso = alert.get('start_at', 'Unkown start time')
                stop_at_iso = alert.get('stop_at', 'Dit bericht is actief!')
                print(f"[INFO] Processing alert ID: {alert_id}")

                start_at_unix = iso_to_unix(start_at_iso) if start_at_iso else None
                stop_at_unix = iso_to_unix(stop_at_iso) if stop_at_iso else None
                print(f"[INFO] Changed ISO timestamp to UNIX")

                if alert_id and not alert_exists(alert_id):
                    save_alert_to_db(alert_id, title, description, start_at_unix, stop_at_unix)

                    await send_alert_to_discord(alert_id, title, start_at_unix, stop_at_unix)
        else:
            print("[ERROR] Unexpected JSON format: 'data' is not a list.")
    except Exception as e:
        print(f"[ERROR] Failed to process API response: {e}")

def alert_exists(alert_id):
    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor() as cursor:
            query = "SELECT COUNT(*) AS count FROM alerts WHERE id = %s"
            cursor.execute(query, (alert_id,))
            result = cursor.fetchone()
            return result['count'] > 0 # pyright: ignore[reportOptionalSubscript, reportArgumentType, reportCallIssue]
    finally:
        conn.close()

def save_alert_to_db(alert_id, title, description, start_at_unix, stop_at_unix):
    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor() as cursor:
            query = "INSERT INTO alerts (id, title, description, start_at_unix, stop_at_unix) VALUES (%s, %s, %s, %s, %s)"
            cursor.execute(query, (alert_id, title, description, start_at_unix, stop_at_unix))
            conn.commit()
    finally:
        conn.close()

async def send_alert_to_discord(alert_id, title, start_at_unix, stop_at_unix):
    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor() as cursor:
            query = "SELECT guild_id, channel_id FROM discord_channels"
            cursor.execute(query)
            channels = cursor.fetchall()

            for channel_entry in channels:
                guild_id = channel_entry['guild_id'] # pyright: ignore[reportArgumentType, reportCallIssue]
                channel_id = channel_entry['channel_id'] # pyright: ignore[reportArgumentType, reportCallIssue]
                
                guild = bot.get_guild(guild_id)
                if not guild:
                    print(f"[WARNING] Guild not found or bot not in guild: {guild_id}")
                    continue

                channel = guild.get_channel(channel_id)
                if not channel:
                    print(f"[WARNING] Channel not found or bot lacks permissions: {channel_id} in guild {guild_id}")
                    continue

                title_match = re.match(r'^[^.]+', title)
                truncated_title = title_match.group(0) if title_match else title[:256]

                embed = discord.Embed(
                    title=f"NL-Alert: {truncated_title}",
                    description=title,
                    color=discord.Color.yellow(),
                )
                embed.add_field(
                    name=f"Start/Eind tijd",
                    value=f'Start: <t:{start_at_unix}:R>\nEind: <t:{stop_at_unix}:R>',
                    inline=False,
                )
                embed.add_field(
                    name="Voor meer info check",
                    value=f"https://actueel.nl-alert.nl/alert/{alert_id}/",
                    inline=True,
                )
                embed.add_field(
                    name="Alert ID",
                    value=f"{alert_id}",
                    inline=True,
                )
                embed.set_footer(text=f"Deze bot is geen onderdeel van de Nederlandse Overheid of NL-Alert en wordt onderhouden door Velvox.")

                if NL_ALERT_IMAGE_URL:
                    embed.set_image(url=NL_ALERT_IMAGE_URL)

                await channel.send(embed=embed)
                print(f"[INFO] message sent in channel {channel_id} in guild {guild_id}")

            await send_embed_to_all_users(bot, embed) # pyright: ignore[reportPossiblyUnboundVariable]
            print(f"[INFO] message sent to individual (once)")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        conn.close()


### EINDE NL ALERT BLOK

### AMBER ALERT BLOK
@tasks.loop(minutes=1)
async def fetch_amber_alerts():    
    try:
        response = requests.get(AMBER_ALERT_API) # pyright: ignore[reportArgumentType]
        print(f"[INFO] Requested Amber Alerts with status code: {response.status_code}")

        if response.status_code == 200:
#            print(f"[DEBUG] Response Content: {response.text[:500]}") # remove the hashtag for debug option
            
            json_response = response.json()

            alerts = json_response if isinstance(json_response, list) else []
            if alerts:
                for alert in alerts:
                    alert_id = alert.get("AlertId")
                    title = alert.get("Message", {}).get("Title", "No Title")
                    description = alert.get("Message", {}).get("Description", "No Description")
                    description_extended = alert.get("Message", {}).get("DescriptionExt", "No Extended Description")
                    read_more = alert.get("Message", {}).get("Readmore_URL", "No Read more URL")
                    image_url = alert.get("Message", {}).get("Media", {}).get("Image", "No Image URL")
                    alert_level = int(alert.get("AlertLevel", 0))
                    time_stamp_unix = alert.get("Sent", "0")

                    if alert_id and not amber_exists(alert_id):
                        save_amber_to_db(alert_id, title, description, description_extended, alert_level, time_stamp_unix, image_url)
                        await send_amber_alert_to_discord(alert_id, title, description, description_extended, alert_level, time_stamp_unix, image_url, read_more)

                print("[INFO] Successfully processed Amber Alerts.")
            else:
                print("[INFO] No alerts found in the JSON response.")
        else:
            print(f"[ERROR] Failed to retrieve Amber Alerts: HTTP {response.status_code}")
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")

def amber_exists(alert_id):
    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor() as cursor:
            query = "SELECT COUNT(*) AS count FROM amber_alerts WHERE id = %s"
            cursor.execute(query, (alert_id,))
            result = cursor.fetchone()
            return result['count'] > 0 # pyright: ignore[reportOptionalSubscript, reportArgumentType, reportCallIssue]
    finally:
        conn.close()

def save_amber_to_db(alert_id, title, description, description_extended, alert_level, time_stamp_unix, image_url):
    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor() as cursor:
            query = """
            INSERT INTO amber_alerts (id, title, description, description_extended, alert_level, timestamp_unix, image_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (alert_id, title, description, description_extended, alert_level, time_stamp_unix, image_url))
            conn.commit()
    finally:
        conn.close()

async def send_amber_alert_to_discord(alert_id, title, description, description_extended, alert_level, time_stamp_unix, image_url, read_more):
    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor() as cursor:
            query = "SELECT guild_id, channel_id FROM discord_channels"
            cursor.execute(query)
            channels = cursor.fetchall()

            for channel_entry in channels:
                guild_id = channel_entry['guild_id'] # pyright: ignore[reportArgumentType, reportCallIssue]
                channel_id = channel_entry['channel_id'] # pyright: ignore[reportArgumentType, reportCallIssue]
                
                guild = bot.get_guild(guild_id)
                if guild:
                    channel = guild.get_channel(channel_id)
                    if channel:
                        alert_type = "Nationaal" if alert_level == 10 else "Regionaal" if alert_level == 5 else "Onbekend"
                        is_it_amber = "AMBER ALERT" if alert_level == 10 else "Vermist Kind Alert" if alert_level == 5 else "Urgentie onbekend"
                        embed = discord.Embed(
                            title=f"{is_it_amber}: {title} is {description_extended} en heeft jou hulp nodig!",
                            description=description,
                            color=discord.Color.orange(),
                        )
                        embed.add_field(name="Type melding", value=alert_type, inline=True)
                        embed.add_field(name="Verstuurd", value=f"<t:{time_stamp_unix}:R>", inline=True)
                        embed.add_field(name="Meer informatie", value=read_more, inline=False)
                        embed.add_field(name="Alert ID", value=f"{alert_id}", inline=True)
                        embed.add_field(name="Checken of deze alert nog actief is?", value=f"Deze discord bot update de alerts niet achteraf dus wilt u checken of deze nog actief is ga naar: {read_more}", inline=False)

                        if image_url:
                            embed.set_image(url=image_url)

                        embed.set_footer(text="Deze bot is geen onderdeel van de overheid en wordt onderhouden door Velvox.")

                        await channel.send(embed=embed)
                        print(f"[INFO] Amber Alert sent to Discord channel {channel_id}.")
                        await send_embed_to_all_users(bot, embed)
    except Exception as e:
        print(f"[ERROR] Failed to send Amber Alert to Discord: {e}")
    finally:
        conn.close()

### EINDE AMBER ALERT BLOK

### POLITIE API V5

POLITIE_API_KEY = "YOUR_API_KEY_HERE"

CASE_TYPE_TRANSLATIONS = {
    "children": "vermiste-kinderen",
    "adults": "vermiste-volwassenen"
}

def extract_kenmerken(signalementen):
    if not signalementen:
        return ""
    personen = []
    for s in signalementen:
        titel = s.get("titel", "Persoon")
        kenmerken_list = []
        for key, value in s.items():
            if key.lower() not in ["titel", "afbeelding"] and value:
                kenmerken_list.append(f"{key}: {value}")
        kenmerken_str = ", ".join(kenmerken_list) if kenmerken_list else "Geen kenmerken beschikbaar"
        personen.append(f"{titel}: {kenmerken_str}")
    return " | ".join(personen)  # separate each person with a pipe

@tasks.loop(minutes=10)
async def fetch_missing_persons():
    print(f"[INFO] Requesting v5 missing cases from Politie API...")

    offset = 0
    per_page = 10
    total = None

    while True:
        full_politie_v5_api_vermist= f"{POLITIE_V5_API_VERMIST}?maxnumberofitems={per_page}&offset={offset}"

        headers = {
            "Accept": "application/json",
        }

        response = requests.get(full_politie_v5_api_vermist, headers=headers)
        print(f"[INFO] Requested data (offset {offset}) → status {response.status_code}")

        if response.status_code in (204, 403):
            print("[INFO]" if response.status_code == 204 else "[ERROR]", "No results or bad API key.")
            break
        if response.status_code != 200:
            print(f"[ERROR] HTTP {response.status_code}: {response.text[:200]}")
            break

        try:
            data = response.json()
            iterator = data.get("iterator", {})
            documenten = data.get("documenten", [])

            if total is None:
                total = iterator.get("total", len(documenten))
                total_pages = math.ceil(total / per_page)
                print(f"[INFO] Found {total} total cases ({total_pages} pages).")

            for case in documenten:
                uid = case.get("uuid")
                title = case.get("titel", "Onbekende Titel")
                last_seen = ", ".join(case.get("locatie", [])) if case.get("locatie") else case.get("plaats", "Onbekende Locatie")
                missing_since = case.get("datum", "Onbekende Datum") or "00-00-0000"
                description = case.get("introductie", "Geen introductie beschikbaar.")
                zaaknummer = case.get("zaaknummer") 
                
                signalementen = case.get("signalementen", [])
                image_url = signalementen[0].get("afbeelding") if signalementen else None

                case_url = case.get("url", "")
                tip_url = case.get("urlTipformulier", "")
                
                kenmerken = extract_kenmerken(signalementen)
                video_url = None
                case_type = case.get("gezochtType")

                print(f"[INFO] Processing case UUID: {uid}")

                if uid and not case_exists(uid):
                    save_case_to_db(uid, title, last_seen, missing_since, description,
                                    image_url, case_url, video_url, kenmerken, case_type, tip_url,
                                    zaaknummer) 
                    
                    await send_case_to_discord(uid, title, last_seen, missing_since,
                                               description, image_url, case_url, video_url,
                                               kenmerken, case_type, tip_url, zaaknummer)

            offset += per_page
            if offset >= total:
                print(f"[INFO] Finished fetching all {total_pages} pages.") # pyright: ignore[reportPossiblyUnboundVariable]
                break

        except Exception as e:
            print(f"[ERROR] Failed to process v5 API response: {e}")
            break



# V5 Save&Send


def case_exists(uid):
    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            query = "SELECT COUNT(*) AS count FROM missing WHERE uid = %s"
            cursor.execute(query, (uid,))
            result = cursor.fetchone()
            return result["count"] > 0 # pyright: ignore[reportOptionalSubscript]
    finally:
        conn.close()

def save_case_to_db(uid, title, last_seen, missing_since, description,
                    image_url, case_url, video_url, kenmerken, case_type, tip_url=None,
                    zaaknummer=None):
    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor() as cursor:
            query = """
                INSERT INTO missing (
                    uid, title, last_seen, missing_since, description,
                    image_url, case_url, video_url, kenmerken, case_type, tip_url, zaaknummer
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (
                uid, title, last_seen, missing_since, description,
                image_url, case_url, video_url, kenmerken, case_type, tip_url, zaaknummer
            ))
            conn.commit()
            print(f"[DB] Saved new {case_type} case {uid} → {title} (zaaknummer: {zaaknummer})")
    except Exception as e:
        print(f"[DB ERROR] Failed to save case {uid}: {e}")
    finally:
        conn.close()


async def send_case_to_discord(uid, title, last_seen, missing_since, description,
                               image_url, case_url, video_url, kenmerken, case_type,
                               tip_url=None, zaaknummer=None):
    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT guild_id, channel_id FROM discord_channels")
            channels = cursor.fetchall()

            # Main embed with first image
            main_embed = discord.Embed(
                title=f"Vermist: {title}",
                description=description,
                color=discord.Color.orange() if case_type == "vermiste-kinderen" else discord.Color.blue(),
                url=case_url
            )
            if image_url:
                main_embed.set_image(url=image_url) 

            main_embed.add_field(name="Laatst gezien in", value=last_seen, inline=True)
            main_embed.add_field(name="Vermist sinds", value=missing_since or "Onbekend", inline=True)
            if kenmerken:
                main_embed.add_field(name="Kenmerken", value=kenmerken, inline=False)
            if tip_url:
                main_embed.add_field(name="Tip doorgeven", value=f"[Klik hier om een tip te geven]({tip_url})", inline=False)
            main_embed.add_field(name="Meer informatie", value=f"[Bekijk op Politie.nl]({case_url})", inline=True)
            main_embed.add_field(name="Zaaknummer", value=f"`{zaaknummer}`", inline=True)
            main_embed.add_field(name="Technische informatie", value=f"UID: `{uid}`", inline=False)
            main_embed.set_footer(text="Deze bot is niet van of in samenwerking met de Nederlandse Politie en wordt onderhouden door Velvox")

        # Send to all configured channels
        for ch in channels:
            guild = bot.get_guild(ch["guild_id"])
            if guild:
                channel = guild.get_channel(ch["channel_id"])
                if channel:
                    await channel.send(embed=main_embed)
                    print(f"[INFO] Sent case '{title}' with image in guild {guild.name} ({ch['guild_id']})")

        # Optional: send main embed individually to all users
        await send_embed_to_all_users(bot, main_embed)

    except Exception as e:
        print(f"[ERROR] Failed to send embed to Discord: {e}")
    finally:
        conn.close()


#####       END NEW API V5

@bot.tree.command(name="setchannel")
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    """Stel het kanaal in waarin je alerts wilt ontvangen"""

    guild_id = interaction.guild.id
    channel_id = channel.id

    if not channel_exists(guild_id, channel_id):
        save_channel_to_db(guild_id, channel_id)
        await interaction.response.send_message(f"Alerts will now be sent to {channel.mention}.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Alerts are already set for {channel.mention}.", ephemeral=True)

def channel_exists(guild_id, channel_id):
    """Check if the channel already exists in the database for the given guild."""
    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor() as cursor:
            query = "SELECT COUNT(*) AS count FROM discord_channels WHERE guild_id = %s AND channel_id = %s"
            cursor.execute(query, (guild_id, channel_id))
            result = cursor.fetchone()
            return result['count'] > 0 # pyright: ignore[reportOptionalSubscript, reportArgumentType, reportCallIssue]
    finally:
        conn.close()

def save_channel_to_db(guild_id, channel_id):
    """Save the guild and channel ID to the database."""
    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor() as cursor:
            query = "INSERT INTO discord_channels (guild_id, channel_id) VALUES (%s, %s)"
            cursor.execute(query, (guild_id, channel_id))
            conn.commit()
    finally:
        conn.close()

@bot.tree.command(name="dmnotify")
async def dm_notify(interaction: discord.Interaction):
    """Opt-in om alerts te ontvangen in je DM."""
    user_id = interaction.user.id

    if not dm_user_exists(user_id):
        save_dm_user_to_db(user_id)
        
        dm_channel = interaction.user.dm_channel
        if not dm_channel:
            try:
                dm_channel = await interaction.user.create_dm()
            except discord.Forbidden:
                await interaction.response.send_message("I cannot send you DMs. Please check your privacy settings.", ephemeral=True)
                return

        try:
            await dm_channel.send("You subscribed to receive alerts in your DMs.")
        except discord.Forbidden:
            await interaction.response.send_message("Hey ik kan je geen DM's sturen. Stuur eerst een bericht naar mij of pas je privacy settings aan!", ephemeral=True)
            return

        await interaction.response.send_message("Je ontvangt vanaf nu berichten in je DM.", ephemeral=True)
    else:
        await interaction.response.send_message("Je ontvangt al berichten in je DM.", ephemeral=True)


@bot.tree.command(name="dmnotifystop")
async def dm_notify_stop(interaction: discord.Interaction):
    """Opt-out om geen alerts te ontvangen in je DM."""
    user_id = interaction.user.id

    if dm_user_exists(user_id):
        remove_dm_user_from_db(user_id)
        await interaction.response.send_message("Je ontvangt geen berichten meer in je DM.", ephemeral=True)
    else:
        await interaction.response.send_message("Je ontvangt geen berichten in je DM.", ephemeral=True)

@bot.tree.command(name="amberalert")
async def amberalert(interaction: discord.Interaction):
    """Vraag de meest recente Amber Alert op."""
    
    try:
        response = requests.get(AMBER_ALERT_API) # pyright: ignore[reportArgumentType]
        print(f"[INFO] Requested (on user interaction) Amber Alerts with status code: {response.status_code}")

        if response.status_code == 200:
            json_response = response.json()
            alerts = json_response if isinstance(json_response, list) else []

            if alerts:
                # Use the first alert from the list. Modify if you want to handle multiple alerts.
                alert = alerts[0]
                alert_id = alert.get("AlertId", "N/A")
                title = alert.get("Message", {}).get("Title", "No Title")
                description = alert.get("Message", {}).get("Description", "No Description")
                description_extended = alert.get("Message", {}).get("DescriptionExt", "No Extended Description")
                read_more = alert.get("Message", {}).get("Readmore_URL", "No Read more URL")
                image_url = alert.get("Message", {}).get("Media", {}).get("Image", "")
                alert_level = int(alert.get("AlertLevel", 0))
                time_stamp_unix = alert.get("Sent", "0")

                alert_type = "Nationaal" if alert_level == 10 else "Regionaal" if alert_level == 5 else "Onbekend"
                is_it_amber = "AMBER ALERT" if alert_level == 10 else "Vermist Kind Alert" if alert_level == 5 else "Urgentie onbekend"
                embed = discord.Embed(
                    title=f"{is_it_amber}: {title} is {description_extended} en heeft jou hulp nodig!",
                    description=description,
                    color=discord.Color.orange(),
                )
                embed.add_field(name="Type melding", value=alert_type, inline=True)
                embed.add_field(name="Verstuurd", value=f"<t:{time_stamp_unix}:R>", inline=True)
                embed.add_field(name="Meer informatie", value=read_more, inline=False)
                embed.add_field(name="Alert ID", value=f"{alert_id}", inline=True)
                embed.add_field(
                    name="Checken of deze alert nog actief is?",
                    value=f"Deze discord bot update de alerts niet achteraf dus wilt u checken of deze nog actief is ga naar: {read_more}",
                    inline=False
                )

                if image_url:
                    embed.set_image(url=image_url)

                embed.set_footer(text="Deze bot is geen onderdeel van de overheid en wordt onderhouden door Velvox.")

                await interaction.response.send_message(embed=embed)
                print(f"[INFO] Bot responded with Amber Alert to /amberalert command.")
                return
            else:
                # No alerts found; respond with an embed stating that
                embed = discord.Embed(
                    title="Geen Amber Alerts",
                    description="Er zijn momenteel geen Amber Alerts.",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed)
                print("[INFO] No Amber Alerts found; responded with a 'no alerts' embed.")
                return
        else:
            # Non-200 status code; inform the user.
            embed = discord.Embed(
                title="Error",
                description=f"Failed to retrieve Amber Alerts: HTTP {response.status_code}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            print(f"[ERROR] Failed to retrieve Amber Alerts: HTTP {response.status_code}")
            return

    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        embed = discord.Embed(
            title="Error",
            description="Er is een onverwachte fout opgetreden bij het ophalen van Amber Alerts.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
        return

def dm_user_exists(user_id):
    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor() as cursor:
            query = "SELECT COUNT(*) AS count FROM discord_dm_users WHERE user_id = %s"
            cursor.execute(query, (user_id,))
            result = cursor.fetchone()
            return result['count'] > 0 # pyright: ignore[reportOptionalSubscript, reportArgumentType, reportCallIssue]
    finally:
        conn.close()

def save_dm_channel_id_to_db(user_id, channel_id):
    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor() as cursor:
            query = "UPDATE discord_dm_users SET dm_channel_id = %s WHERE user_id = %s"
            cursor.execute(query, (channel_id, user_id))
            conn.commit()
    finally:
        conn.close()

def save_dm_user_to_db(user_id):
    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor() as cursor:
            query = "INSERT INTO discord_dm_users (user_id) VALUES (%s)"
            cursor.execute(query, (user_id,))
            conn.commit()
    finally:
        conn.close()


def remove_dm_user_from_db(user_id):
    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor() as cursor:
            query = "DELETE FROM discord_dm_users WHERE user_id = %s"
            cursor.execute(query, (user_id,))
            conn.commit()
    finally:
        conn.close()

bot.run(BOT_TOKEN)