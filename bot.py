import pymysql
import discord
from discord.ext import commands, tasks
from datetime import datetime
import itertools
import config
import requests
import re
import xml.etree.ElementTree as ET

intents = discord.Intents.default()
intents.message_content = False
intents.members = False

bot = commands.Bot(command_prefix='/', intents=intents)

db_config = config.db_config

activities = itertools.cycle([
    discord.Activity(type=discord.ActivityType.watching, name="NL-Alerts"),
    discord.Activity(type=discord.ActivityType.watching, name="Amber Alerts"),
    discord.Activity(type=discord.ActivityType.playing, name="Politie V4 API")
])

@tasks.loop(seconds=5)
async def change_activity():
    current_activity = next(activities)
    await bot.change_presence(activity=current_activity)

@bot.event
async def on_ready():
    print(f'[INFO] Logged in as {bot.user}')
    change_activity.start()
    fetch_nl_alerts.start()
    fetch_missing_children_cases.start()
    fetch_missing_adult_cases.start()
    fetch_amber_alerts.start()
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
            user = await bot.fetch_user(user_id['user_id'])
            await user.send(embed=embed)

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        cursor.close()
        connection.close()

### NL ALERT BLOK
@tasks.loop(minutes=2)
async def fetch_nl_alerts():
    url = "https://api.public-warning.app/api/v1/providers/nl-alert/alerts"
    response = requests.get(url)
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
            return result['count'] > 0
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
                guild_id = channel_entry['guild_id']
                channel_id = channel_entry['channel_id']
                
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

                if config.nl_alert_image_url:
                    embed.set_image(url=config.nl_alert_image_url)

                await channel.send(embed=embed)
                print(f"[INFO] message sent in channel {channel_id} in guild {guild_id}")

            await send_embed_to_all_users(bot, embed)
            print(f"[INFO] message sent to individual (once)")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        conn.close()


### EINDE NL ALERT BLOK

### AMBER ALERT BLOK
@tasks.loop(minutes=1)
async def fetch_amber_alerts():
    url = "https://services.burgernet.nl/landactiehost/api/test/alerts"
    
    try:
        response = requests.get(url)
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
            return result['count'] > 0
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
                guild_id = channel_entry['guild_id']
                channel_id = channel_entry['channel_id']
                
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

### EINGE AMBER ALERT BLOK

### POLITIE API V4 VERMISTE KINDEREN
@tasks.loop(minutes=10)
async def fetch_missing_children_cases():
    url = "https://api.politie.nl/v4/vermist/vermistekinderen?language=nl&radius=5.0&maxnumberofitems=10&offset=0"
    response = requests.get(url)
    print(f"[INFO] Requested missing children data with status code: {response.status_code}")

    try:
        json_response = response.json()
        children_cases = json_response.get('vermisten', [])

        if isinstance(children_cases, list):
            for case in children_cases:
                uid = case.get('uid')
                title = case.get('titel', 'Unknown Title')
                last_seen = case.get('laatstgezienin', 'Unknown Location')
                missing_since = case.get('vermistsinds', 'Unknown Date')
                description = case.get('introductie', 'No Introduction')
                image_url = case['afbeeldingen'][0]['url'] if case.get('afbeeldingen') else None
                case_url = case.get('url', '')
                video_url = case['videos'][0]['url'] if case.get('videos') else None
                kenmerken = extract_kenmerken(case.get('signalementen', []))

                print(f"[INFO] Processing child case UID: {uid}")

                if uid and not case_exists(uid, "children"):
                    save_case_to_db(uid, title, last_seen, missing_since, description, image_url, case_url, video_url, kenmerken, "children")
                    await send_case_to_discord(uid, title, last_seen, missing_since, description, image_url, case_url, video_url, kenmerken, "children")
        else:
            print("[ERROR] Unexpected JSON format: 'vermisten' is not a list.")
    except Exception as e:
        print(f"[ERROR] Failed to process API response: {e}")

### EINDE POLITIE API V4 VERMISTE KINDEREN

### POLITIE API V4 VERMISTE VOLWASSENEN
@tasks.loop(minutes=10)
async def fetch_missing_adult_cases():
    url = "https://api.politie.nl/v4/vermist/vermistevolwassenen?language=nl&radius=5.0&maxnumberofitems=10&offset=0"
    response = requests.get(url)
    print(f"[INFO] Requested missing adults data with status code: {response.status_code}")

    try:
        json_response = response.json()
        adult_cases = json_response.get('vermisten', [])

        if isinstance(adult_cases, list):
            for case in adult_cases:
                uid = case.get('uid')
                title = case.get('titel', 'Unknown Title')
                last_seen = case.get('laatstgezienin', 'Unknown Location')
                missing_since = case.get('vermistsinds', 'Unknown Date')
                if not missing_since or missing_since.strip() == '':
                    missing_since = "00-00-0000"

                description = case.get('introductie', 'No Introduction')
                image_url = case['afbeeldingen'][0]['url'] if case.get('afbeeldingen') else None
                case_url = case.get('url', '')
                video_url = case['videos'][0]['url'] if case.get('videos') else None
                kenmerken = extract_kenmerken(case.get('signalementen', []))

                print(f"[INFO] Processing adult case UID: {uid}")

                if uid and not case_exists(uid, "adults"):
                    save_case_to_db(uid, title, last_seen, missing_since, description, image_url, case_url, video_url, kenmerken, "adults")
                    await send_case_to_discord(uid, title, last_seen, missing_since, description, image_url, case_url, video_url, kenmerken, "adults")
        else:
            print("[ERROR] Unexpected JSON format: 'vermisten' is not a list.")
    except Exception as e:
        print(f"[ERROR] Failed to process API response: {e}")


### EINDE POLITIE API V4 VERMISTE VOLWASSENEN

### GEDEELDE FUNCTIES VOOR VERMISTE KINDEREN EN VERMISTE VOLWASSENEN

CASE_TYPE_TRANSLATIONS = {
    "children": "Kind",
    "adults": "Volwassene"
}

def save_case_to_db(uid, title, last_seen, missing_since, description, image_url, case_url, video_url, kenmerken, case_type):
    conn = pymysql.connect(**db_config)
    table_name = f"missing_{case_type}"
    try:
        with conn.cursor() as cursor:
            query = f"""
                INSERT INTO {table_name} (uid, title, last_seen, missing_since, description, image_url, case_url, video_url, kenmerken)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (uid, title, last_seen, missing_since, description, image_url, case_url, video_url, kenmerken))
            conn.commit()
    finally:
        conn.close()

def case_exists(uid, case_type):
    conn = pymysql.connect(**db_config)
    table_name = f"missing_{case_type}"
    try:
        with conn.cursor() as cursor:
            query = f"SELECT COUNT(*) AS count FROM {table_name} WHERE uid = %s"
            cursor.execute(query, (uid,))
            result = cursor.fetchone()
            return result['count'] > 0
    finally:
        conn.close()

async def send_case_to_discord(uid, title, last_seen, missing_since, description, image_url, case_url, video_url, kenmerken, case_type):
    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor() as cursor:
            query = "SELECT guild_id, channel_id FROM discord_channels"
            cursor.execute(query)
            channels = cursor.fetchall()

            for channel_entry in channels:
                guild_id = channel_entry['guild_id']
                channel_id = channel_entry['channel_id']

                guild = bot.get_guild(guild_id)
                if guild:
                    channel = guild.get_channel(channel_id)
                    if channel:
                        translated_case_type = CASE_TYPE_TRANSLATIONS.get(case_type, case_type)

                        if missing_since == "00-00-0000":
                            missing_since_display = "Vermist sinds is onbekend"
                        else:
                            missing_since_display = missing_since

                        embed = discord.Embed(
                            title=f"Vermist {translated_case_type.capitalize()}: {title}",
                            description=description,
                            color=discord.Color.orange() if case_type == "children" else discord.Color.blue(),
                        )
                        embed.add_field(name="Laatst gezien in", value=last_seen, inline=True)
                        embed.add_field(name="Vermist sinds", value=missing_since_display, inline=True)
                        if kenmerken:
                            embed.add_field(name="Kenmerken", value=kenmerken, inline=False)
                        embed.add_field(name="Meer informatie over de zaak", value=f"[Informatie via Politie.nl]({case_url})", inline=True)
                        if video_url:
                            embed.add_field(name="Bekijk de video", value=f"[Bekijk de informatie video]({video_url})", inline=True)
                        embed.add_field(name="Technische informatie", value=f"UID: `{uid}`", inline=False)
                        if image_url:
                            embed.set_thumbnail(url=image_url)
                        embed.set_footer(text=f"Deze bot is niet van de Nederlandse Politie en wordt onderhouden door Velvox")

                        await channel.send(embed=embed)
                        print(f"[INFO] message sent in channel {channel_id} in guild {guild_id}")

            await send_embed_to_all_users(bot, embed)
            print(f"[INFO] message sent to individual")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        conn.close()


def extract_kenmerken(signalementen):
    """Extract 'persoonskenmerken' as a formatted string."""
    kenmerken = []
    
    if not isinstance(signalementen, list):
        return "Kenmerken niet bekend"
    
    for signalement in signalementen:
        persoonskenmerken = signalement.get('persoonskenmerken', [])
        
        if not isinstance(persoonskenmerken, list):
            continue
        
        for kenmerk in persoonskenmerken:
            label = kenmerk.get('label', 'Unknown Label')
            waarde = kenmerk.get('waarde', 'Unknown Value')
            kenmerken.append(f"__*{label}:*__ {waarde}")
    
    return "\n".join(kenmerken) if kenmerken else "Kenmerken niet bekend"
### EINGE GEDEELDE FUNCTIES VOOR VERMISTE KINDEREN EN VERMISTE VOLWASSENEN

@bot.tree.command(name="setchannel")
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    """Set the channel for receiving NL-alerts."""

    guild_id = interaction.guild.id
    channel_id = channel.id

    if not channel_exists(guild_id, channel_id):
        save_channel_to_db(guild_id, channel_id)
        await interaction.response.send_message(f"NL-Alerts will now be sent to {channel.mention}.", ephemeral=True)
    else:
        await interaction.response.send_message(f"NL-Alerts are already set for {channel.mention}.", ephemeral=True)

def channel_exists(guild_id, channel_id):
    """Check if the channel already exists in the database for the given guild."""
    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor() as cursor:
            query = "SELECT COUNT(*) AS count FROM discord_channels WHERE guild_id = %s AND channel_id = %s"
            cursor.execute(query, (guild_id, channel_id))
            result = cursor.fetchone()
            return result['count'] > 0
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
    """Opt-in to receive NL-Alerts in your DMs."""
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
            await dm_channel.send("You subscribed to receive NL-Alerts in your DMs.")
        except discord.Forbidden:
            await interaction.response.send_message("Hey ik kan je geen DM's sturen. Stuur eerst een bericht naar mij of pas je privacy settings aan!", ephemeral=True)
            return

        await interaction.response.send_message("Je ontvangt vanaf nu berichten in je DM.", ephemeral=True)
    else:
        await interaction.response.send_message("Je ontvangt al berichten in je DM.", ephemeral=True)


@bot.tree.command(name="dmnotifystop")
async def dm_notify_stop(interaction: discord.Interaction):
    """Opt-out of receiving NL-Alerts in your DMs."""
    user_id = interaction.user.id

    if dm_user_exists(user_id):
        remove_dm_user_from_db(user_id)
        await interaction.response.send_message("Je ontvangt geen berichten meer in je DM.", ephemeral=True)
    else:
        await interaction.response.send_message("Je ontvangt geen berichten in je DM.", ephemeral=True)

def dm_user_exists(user_id):
    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor() as cursor:
            query = "SELECT COUNT(*) AS count FROM discord_dm_users WHERE user_id = %s"
            cursor.execute(query, (user_id,))
            result = cursor.fetchone()
            return result['count'] > 0
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

bot.run(config.BOT_TOKEN)
