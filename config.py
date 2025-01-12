import pymysql
# Bot settings
nl_alert_image_url = ""
# Bot configuration
BOT_TOKEN = ''
# MySQL configuration
MYSQLUSER = 'databaseuser'
MYSQLPASSOWRD = 'databasepasswd'
MYSQLDATABASE = 'databasename'
MYSQLHOST = 'databasehost'
# Static Database config DONT CHANGE!!
db_config = {
    'host': MYSQLHOST,  # Change this to your MySQL host
    'user': MYSQLUSER,  # Your MySQL username
    'password': MYSQLPASSOWRD,  # Your MySQL password
    'database': MYSQLDATABASE,  # Your database name
    'cursorclass': pymysql.cursors.DictCursor,
}
