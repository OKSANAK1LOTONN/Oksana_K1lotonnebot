import os, time, random, sqlite3, logging
from contextlib import contextmanager
from datetime import datetime
import chess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, LabeledPrice
from telegram.constants import ChatType
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, PreCheckoutQueryHandler, ContextTypes, filters

TOKEN=os.environ['BOT_TOKEN']; WEBHOOK_URL=os.environ['WEBHOOK_URL'].rstrip('/'); PORT=int(os.getenv('PORT','10000')); DB_PATH=os.getenv('DB_PATH','game.db')
ADMIN_IDS={int(x.strip()) for x in os.getenv('ADMIN_IDS','').split(',') if x.strip().isdigit()}
logging.basicConfig(level=logging.INFO); log=logging.getLogger('oksana')
FACTORIES=[('Корыто 🪾',100),('Болото с вяленой селёдью 🐟',180),('Вываривание жира при монастыре «Трисися» 🪔',300),('Ахуевшая лодочка с капустой 🥬',500),('Сломанный уличный унитаз на колёсиках 🚾',800),('Рынок зубов 🦷',1250),('ТЦ «Дикси» 🫩',1900),('Ставропольский государственный университет имени Ленина 💥',2800),('Магистратура «Еврейское логово» 🎓',4100),('Карманный мегаполис 🏙️',5900),('Молекулярная кухня «Них#я себе!» 🧪',8400),('Дирижабль «Пархай и падай» 🎈',11800),('ТАОБАО 🛍️',16400),('Ракета! 🚀',22600),('Лунная колония «Ореол соска» 🌕',31000),('Центральный банк Солнечной системы MAMKASAMKA.IBAN 🪐',42000),('Потеря сознания отжира 🫠',56500),('Кубическое измерение 🔷',75500),('Полигональное понятие рецидива 🌀',100000),('Бесконечность? ♾️',132000)]
# item tuples: name, rarity, income %, speed multiplier, theft share %, protection %
ITEMS={
'artifact':[('Дубовый аксельбант 🪵','Хуйня',2,1,0,0),('Значок завхозки 🏷️','Normal',5,1,0,0),('Амулет главного технолога 💜','Epic',12,1,0,0),('Корона нефтяной жабы 👑','Mythic',25,1,0,0),('Медаль миллионного производства 🏆','Legendary',50,1,0,0),('МИКРОФОН МАМКА-САМКА 🎤','Holy shit!',0,5,0,0),('Картонный щит бухгалтера 🛡️','Normal',0,1,0,10),('Неприкосновенный запас 🔐','Epic',0,1,0,20),('Абсолютный сейф MAMKASAMKA 💎','Holy shit!',0,1,0,100)],
'weapon':[('Ржавая ложка 🥄','Хуйня',0,1,5,0),('Тапок завхозки 🩴','Normal',1,1,10,0),('Нунчаки из сосисок 🌭','Epic',3,1,20,0),('Кувалда бухгалтера 🔨','Mythic',5,1,35,0),('Золотой лом MAMKASAMKA 🪙','Legendary',8,1,50,0),('Межгалактический грабитель 🛸','Holy shit!',10,1,70,0)]}

@contextmanager
def db():
 c=sqlite3.connect(DB_PATH,timeout=20,isolation_level=None); c.row_factory=sqlite3.Row; c.execute('PRAGMA busy_timeout=20000'); c.execute('PRAGMA foreign_keys=ON')
 try: yield c
 finally: c.close()
def init_db():
 with db() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS players(user_id INTEGER PRIMARY KEY,name TEXT DEFAULT '',username TEXT DEFAULT '',nick TEXT DEFAULT '',factory_name TEXT DEFAULT '',balance INTEGER DEFAULT 0,level INTEGER DEFAULT 1,stored REAL DEFAULT 0,last_ts REAL DEFAULT 0,premium_until REAL DEFAULT 0,blocked INTEGER DEFAULT 0);
  CREATE TABLE IF NOT EXISTS stats(user_id INTEGER PRIMARY KEY,calories INTEGER DEFAULT 0,stolen INTEGER DEFAULT 0,thefts INTEGER DEFAULT 0,wins INTEGER DEFAULT 0,losses INTEGER DEFAULT 0);
  CREATE TABLE IF NOT EXISTS inventory(item_id INTEGER PRIMARY KEY AUTOINCREMENT,owner_id INTEGER,name TEXT,rarity TEXT,kind TEXT,income REAL DEFAULT 0,speed REAL DEFAULT 1,steal REAL DEFAULT 0,protect REAL DEFAULT 0,exclusive INTEGER DEFAULT 0);
  CREATE TABLE IF NOT EXISTS whitelist(user_id INTEGER PRIMARY KEY,added_by INTEGER,added_at REAL);
  CREATE TABLE IF NOT EXISTS cooldowns(user_id INTEGER,action TEXT,until_ts REAL,PRIMARY KEY(user_id,action));
  CREATE TABLE IF NOT EXISTS promos(code TEXT PRIMARY KEY,amount INTEGER,hidden INTEGER DEFAULT 0,admin_only INTEGER DEFAULT 0,active INTEGER DEFAULT 1);
  CREATE TABLE IF NOT EXISTS promo_uses(code TEXT,user_id INTEGER,used_at REAL,PRIMARY KEY(code,user_id));
  CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY AUTOINCREMENT,a INTEGER,b INTEGER,acoin INTEGER DEFAULT 0,bcoin INTEGER DEFAULT 0,aa INTEGER DEFAULT 0,ba INTEGER DEFAULT 0,status TEXT DEFAULT 'open',created REAL);
  CREATE TABLE IF NOT EXISTS trade_items(trade_id INTEGER,item_id INTEGER,owner_id INTEGER,PRIMARY KEY(trade_id,item_id));
  CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,actor INTEGER,target INTEGER,action TEXT,details TEXT,ts REAL);
  CREATE TABLE IF NOT EXISTS chess_games(id INTEGER PRIMARY KEY AUTOINCREMENT,w INTEGER,b INTEGER,stake INTEGER,fen TEXT,status TEXT,created REAL);
  ''')
  for row in [('OKSANAKILOTONNALIVE',100,0,0,1),('MAMKASAMKAPROD',100,0,0,1),('DODOPIZDA',50,0,0,1),('PRIMEME',100000000000000000,1,0,1),('ONLYFANS2015',0,1,1,1)]: c.execute('INSERT OR IGNORE INTO promos(code,amount,hidden,admin_only,active) VALUES(?,?,?,?,?)',row)
def audit(actor,target,action,details=''):
 with db() as c: c.execute('INSERT INTO audit(actor,target,action,details,ts) VALUES(?,?,?,?,?)',(actor,target,action,str(details)[:800],time.time()))
def ensure(u):
 now=time.time()
 with db() as c:
  c.execute('INSERT OR IGNORE INTO players(user_id,name,username,last_ts) VALUES(?,?,?,?)',(u.id,u.full_name or str(u.id),u.username or '',now))
  c.execute('UPDATE players SET name=?,username=? WHERE user_id=?',(u.full_name or str(u.id),u.username or '',u.id)); c.execute('INSERT OR IGNORE INTO stats(user_id) VALUES(?)',(u.id,))
def getp(uid):
 with db() as c:return c.execute('SELECT * FROM players WHERE user_id=?',(uid,)).fetchone()
def admin(uid):return uid in ADMIN_IDS
def locked(uid):
 p=getp(uid); return not p or bool(p['blocked'])
def produce(uid):
 now=time.time()
 with db() as c:
  c.execute('BEGIN IMMEDIATE'); p=c.execute('SELECT * FROM players WHERE user_id=?',(uid,)).fetchone()
  if not p:c.execute('ROLLBACK');return None
  level=max(1,min(20,p['level'])); base=FACTORIES[level-1][1]
  its=c.execute('SELECT income,speed FROM inventory WHERE owner_id=?',(uid,)).fetchall(); inc=sum(x['income'] for x in its); speed=max([1]+[x['speed'] for x in its]); premium=p['premium_until']>now
  rate=base*(1+inc/100)*speed*(2 if premium else 1); cap=base*6*(1+inc/100)*(2 if premium else 1)
  stored=min(cap,float(p['stored'])+max(0,now-p['last_ts'])*rate/3600)
  c.execute('UPDATE players SET stored=?,last_ts=? WHERE user_id=?',(stored,now,uid)); c.execute('COMMIT')
  return {'p':p,'rate':rate,'cap':cap,'stored':stored,'inc':inc,'speed':speed}
def menu():return InlineKeyboardMarkup([[InlineKeyboardButton('🏭 Завод',callback_data='factory'),InlineKeyboardButton('👤 Профиль',callback_data='profile')],[InlineKeyboardButton('📦 Собрать кило',callback_data='collect'),InlineKeyboardButton('⬆️ Улучшить',callback_data='upgrade')],[InlineKeyboardButton('🎒 Инвентарь',callback_data='inventory'),InlineKeyboardButton('🏆 Топы',callback_data='tops')],[InlineKeyboardButton('🎲 Игры',callback_data='games'),InlineKeyboardButton('🤝 Трейды',callback_data='tradehelp')],[InlineKeyboardButton('⭐ Премиум',callback_data='premium'),InlineKeyboardButton('🎟 Промокод',callback_data='promohelp')]])
def trade_menu(tid,uid):return InlineKeyboardMarkup([[InlineKeyboardButton('➕ Кило',callback_data=f'tcoin:{tid}:{uid}'),InlineKeyboardButton('➕ Артефакт',callback_data=f'titem:{tid}:{uid}:artifact')],[InlineKeyboardButton('➕ Оружие',callback_data=f'titem:{tid}:{uid}:weapon')],[InlineKeyboardButton('🔄 Обновить',callback_data=f'tview:{tid}:{uid}')],[InlineKeyboardButton('✅ Подтвердить',callback_data=f'taccept:{tid}:{uid}'),InlineKeyboardButton('❌ Отклонить',callback_data=f'tdecline:{tid}:{uid}')]])
async def start(update,ctx):
 u=update.effective_user;ensure(u)
 if locked(u.id):return await update.effective_message.reply_text('⛔ Доступ ограничен.')
 await update.effective_message.reply_text('🍶 Добро пожаловать в Oksana Kiloton!\nЗаводы, кило, предметы, трейды и игры — всё здесь.',reply_markup=menu())
 if update.effective_chat.type==ChatType.PRIVATE: await update.effective_message.reply_text('Быстрое меню',reply_markup=ReplyKeyboardMarkup([[KeyboardButton('🏭 Завод'),KeyboardButton('👤 Профиль')],[KeyboardButton('📦 Собрать кило'),KeyboardButton('⬆️ Улучшить')],[KeyboardButton('🎒 Инвентарь'),KeyboardButton('🏆 Топы')],[KeyboardButton('🎲 Игры'),KeyboardButton('🤝 Трейды')]],resize_keyboard=True))
async def factory_msg(msg,uid):
 x=produce(uid);p=getp(uid);lvl=p['level'];cost=FACTORIES[lvl][1]*10 if lvl<20 else 0
 left=max(0,int((x['cap']-x['stored'])/max(.00001,x['rate'])*3600));name=p['factory_name'] or FACTORIES[lvl-1][0]
 await msg.reply_text(f'🏭 {name}\nУровень: {lvl}/20\n💰 Баланс: {p["balance"]:,} кило\n⚙️ Доход: {x["rate"]:,.2f}/час ({x["rate"]/60:,.3f}/мин)\n📦 Хранилище: {x["stored"]:,.2f}/{x["cap"]:,.2f}\n⏳ До заполнения: {left//3600} ч {(left%3600)//60} мин\nБонус дохода: +{x["inc"]}% · скорость ×{x["speed"]}\n'+(f'Следующее улучшение: {cost:,} кило' if lvl<20 else 'Максимальный уровень!'),reply_markup=menu())
async def profile_msg(msg,uid):
 p=getp(uid);produce(uid)
 with db() as c:
  s=c.execute('SELECT * FROM stats WHERE user_id=?',(uid,)).fetchone();n=c.execute('SELECT COUNT(*) n FROM inventory WHERE owner_id=?',(uid,)).fetchone()['n']
 nick=p['nick'] or p['name'];nick=('👑 Герцогиня '+nick) if p['premium_until']>time.time() else nick
 await msg.reply_text(f'👤 {nick}\nID: {uid}\nЗавод: {p["factory_name"] or FACTORIES[p["level"]-1][0]}\nУровень: {p["level"]}/20\nБаланс: {p["balance"]:,} кило\nПредметов: {n}\nКалории заработано: {s["calories"]:,}\nКраж: {s["thefts"]} · украдено {s["stolen"]:,}\nПобед/поражений: {s["wins"]}/{s["losses"]}\nПремиум: {"активен" if p["premium_until"]>time.time() else "нет"}',reply_markup=menu())
async def collect_msg(msg,uid):
 now=time.time()
 with db() as c:
  c.execute('BEGIN IMMEDIATE');p=c.execute('SELECT * FROM players WHERE user_id=?',(uid,)).fetchone()
  if not p:c.execute('ROLLBACK');return await msg.reply_text('Сначала открой бота через /start.')
  lvl=max(1,min(20,p['level']));base=FACTORIES[lvl-1][1];its=c.execute('SELECT income,speed FROM inventory WHERE owner_id=?',(uid,)).fetchall();inc=sum(i['income'] for i in its);speed=max([1]+[i['speed'] for i in its]);prem=p['premium_until']>now;rate=base*(1+inc/100)*speed*(2 if prem else 1);cap=base*6*(1+inc/100)*(2 if prem else 1)
  stored=min(cap,float(p['stored'])+max(0,now-p['last_ts'])*rate/3600);amount=int(stored);balance=p['balance']+amount
  c.execute('UPDATE players SET balance=balance+?,stored=?,last_ts=? WHERE user_id=?',(amount,stored-amount,now,uid));c.execute('UPDATE stats SET calories=calories+? WHERE user_id=?',(amount,uid));c.execute('COMMIT')
 await msg.reply_text(f'📦 Собрано {amount:,} кило! Баланс: {balance:,}',reply_markup=menu())
async def upgrade_msg(msg,uid):
 produce(uid);p=getp(uid);lvl=p['level']
 if lvl>=20:return await msg.reply_text('♾️ Уже 20-й уровень!')
 cost=FACTORIES[lvl][1]*10
 with db() as c:
  c.execute('BEGIN IMMEDIATE');fresh=c.execute('SELECT balance,level FROM players WHERE user_id=?',(uid,)).fetchone()
  if fresh['balance']<cost:c.execute('ROLLBACK');return await msg.reply_text(f'Не хватает кило: нужно {cost:,}, есть {fresh["balance"]:,}.')
  c.execute('UPDATE players SET balance=balance-?,level=level+1,last_ts=? WHERE user_id=?',(cost,time.time(),uid));c.execute('COMMIT')
 await msg.reply_text(f'🎉 Новый завод: {FACTORIES[lvl][0]}\nУровень {lvl+1}. Цена: {cost:,} кило.',reply_markup=menu())
async def inventory_msg(msg,uid):
 with db() as c:rows=c.execute('SELECT * FROM inventory WHERE owner_id=? ORDER BY item_id',(uid,)).fetchall()
 if not rows:return await msg.reply_text('🎒 Инвентарь пуст. Предметы выдаются событиями, конкурсами или администратором.')
 lines=['🎒 Инвентарь:']
 for i in rows:lines.append(f'#{i["item_id"]} {i["name"]} [{i["rarity"]}] · доход +{i["income"]}% · скорость ×{i["speed"]} · кража {i["steal"]}% · защита {i["protect"]}%'+(' · ЭКСКЛЮЗИВ' if i['exclusive'] else ''))
 await msg.reply_text('\n'.join(lines),reply_markup=menu())
async def tops_msg(msg):
 with db() as c:
  rich=c.execute('SELECT p.user_id,COALESCE(NULLIF(p.nick,""),p.name) nm,p.balance FROM players p WHERE blocked=0 ORDER BY balance DESC LIMIT 10').fetchall();cal=c.execute('SELECT p.user_id,COALESCE(NULLIF(p.nick,""),p.name) nm,s.calories FROM stats s JOIN players p USING(user_id) WHERE p.blocked=0 ORDER BY s.calories DESC LIMIT 10').fetchall()
 fmt=lambda rows,key:'\n'.join(f'{i}. {r["nm"]} (ID {r["user_id"]}) — {r[key]:,}' for i,r in enumerate(rows,1)) or 'Пока пусто'
 await msg.reply_text('🏆 ТОП БАЛАНСА\n'+fmt(rich,'balance')+'\n\n🍽 ТОП КАЛОРИЙ\n'+fmt(cal,'calories'),reply_markup=menu())
async def games_msg(msg):
 await msg.reply_text('🎮 Подпольный клуб БДСМ-монахинь Донецка\nВыбери игру:',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🐖 Жирная рулька',callback_data='rulka')],[InlineKeyboardButton('🎲 Кости',callback_data='dice')],[InlineKeyboardButton('♟ Шахматы',callback_data='chesshelp')],[InlineKeyboardButton('⬅️ Меню',callback_data='menu')]]))
async def promo_msg(msg,uid,code):
 code=code.strip().upper()
 with db() as c:
  r=c.execute('SELECT * FROM promos WHERE code=? AND active=1',(code,)).fetchone()
  if not r:return await msg.reply_text('❌ Код не найден или отключён.')
  if r['admin_only'] and not admin(uid):return await msg.reply_text('❌ Код недействителен.')
  if code=='ONLYFANS2015':
   if not admin(uid):return await msg.reply_text('❌ Код недействителен.')
   audit(uid,uid,'admin_panel_code','opened');return await admin_panel(msg,uid)
  if code!='PRIMEME' and c.execute('SELECT 1 FROM promo_uses WHERE code=? AND user_id=?',(code,uid)).fetchone():return await msg.reply_text('Этот код уже использован.')
  c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM promos WHERE code=? AND active=1',(code,)).fetchone()
  if code!='PRIMEME' and c.execute('SELECT 1 FROM promo_uses WHERE code=? AND user_id=?',(code,uid)).fetchone():c.execute('ROLLBACK');return await msg.reply_text('Этот код уже использован.')
  if code!='PRIMEME':c.execute('INSERT INTO promo_uses VALUES(?,?,?)',(code,uid,time.time()))
  c.execute('UPDATE players SET balance=MIN(9000000000000000000,balance+?) WHERE user_id=?',(r['amount'],uid));c.execute('COMMIT')
 audit(uid,uid,'promo_redeemed',code);await msg.reply_text(f'🎟 Активировано! Начислено {r["amount"]:,} кило.')
async def premium_msg(msg):
 await msg.reply_text('⭐ Премиум-пасс: 15 Telegram Stars. Статус «Герцогиня» и ×2 награды завода на 10 дней и 12 часов.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⭐ Купить за 15 Stars',callback_data='buypremium')]]))
async def buy_premium(update,ctx):
 q=update.callback_query;await q.answer()
 try:await ctx.bot.send_invoice(q.from_user.id,'Премиум-пасс Oksana Kiloton','Герцогиня и ×2 награды завода на 10 дней и 12 часов.',f'premium:{q.from_user.id}:{int(time.time())}','', 'XTR',[LabeledPrice('Премиум-пасс',15)])
 except TelegramError:await q.message.reply_text('Не удалось открыть оплату. Проверь настройки Telegram Stars.')
async def precheckout(update,ctx):
 q=update.pre_checkout_query;parts=q.invoice_payload.split(':')
 await q.answer(ok=len(parts)>1 and parts[0]=='premium' and parts[1]==str(q.from_user.id),error_message='Не удалось подтвердить платёж.')
async def paid(update,ctx):
 u=update.effective_user
 if not update.effective_message.successful_payment:return
 with db() as c:c.execute('UPDATE players SET premium_until=MAX(premium_until,?)+? WHERE user_id=?',(time.time(),10.5*86400,u.id))
 audit(u.id,u.id,'premium_purchase','Stars');await update.effective_message.reply_text('👑 Премиум активирован на 10 дней и 12 часов!')
async def theft(msg,uid,target,amount):
 if uid==target:return await msg.reply_text('Нельзя воровать у себя.')
 if amount<100 or amount>1000:return await msg.reply_text('Сумма должна быть от 100 до 1 000 кило.')
 with db() as c:
  t=c.execute('SELECT * FROM players WHERE user_id=?',(target,)).fetchone()
  if not t:return await msg.reply_text('Игрок не найден. Он должен запустить бота.')
  if t['blocked']:return await msg.reply_text('Игрок недоступен.')
  if admin(target) or c.execute('SELECT 1 FROM whitelist WHERE user_id=?',(target,)).fetchone():return await msg.reply_text('🛡️ Этот игрок в белом списке и защищён от краж.')
  cd=c.execute('SELECT until_ts FROM cooldowns WHERE user_id=? AND action="theft"',(uid,)).fetchone()
  if cd and cd[0]>time.time():
   sec=int(cd[0]-time.time());return await msg.reply_text(f'⏳ Следующая кража через {sec//60} мин {sec%60} сек.')
  weapons=c.execute('SELECT steal FROM inventory WHERE owner_id=?',(uid,)).fetchall();share=min(70,max(5,5+sum(x['steal'] for x in weapons)))
  defenses=c.execute('SELECT protect FROM inventory WHERE owner_id=?',(target,)).fetchall();defense=min(100,sum(x['protect'] for x in defenses))
  actual=min(int(amount*share/100*(1-defense/100)),t['balance'])
  if actual<=0:return await msg.reply_text('🛡️ Защита сработала или у игрока нет доступных кило.')
  c.execute('BEGIN IMMEDIATE');t=c.execute('SELECT balance FROM players WHERE user_id=?',(target,)).fetchone()
  if not t or t['balance']<actual:c.execute('ROLLBACK');return await msg.reply_text('Баланс цели изменился. Попробуй позже.')
  c.execute('UPDATE players SET balance=balance-? WHERE user_id=?',(actual,target));c.execute('UPDATE players SET balance=balance+? WHERE user_id=?',(actual,uid));c.execute('INSERT INTO cooldowns VALUES(?,?,?) ON CONFLICT(user_id,action) DO UPDATE SET until_ts=excluded.until_ts',(uid,'theft',time.time()+3600));c.execute('UPDATE stats SET stolen=stolen+?,thefts=thefts+1 WHERE user_id=?',(actual,uid));c.execute('COMMIT')
 audit(uid,target,'theft',f'request={amount};share={share};actual={actual}')
 await msg.reply_text(f'🦹 Кража успешна! Доля {share}% от выбранной суммы. Добыча: {actual:,} кило. Повтор через час.')
 try:await msg.get_bot().send_message(target,f'⚠️ У тебя украли {actual:,} кило. Проверь защиту.')
 except TelegramError:pass
async def create_trade(msg,uid,target):
 if uid==target:return await msg.reply_text('Нельзя торговать с собой.')
 if not getp(target):return await msg.reply_text('Игрок должен сначала открыть бота через /start.')
 if locked(uid) or locked(target):return await msg.reply_text('Трейд недоступен одному из игроков.')
 with db() as c:cur=c.execute('INSERT INTO trades(a,b,created) VALUES(?,?,?)',(uid,target,time.time()));tid=cur.lastrowid
 audit(uid,target,'trade_created',tid);await msg.reply_text(f'🤝 Трейд #{tid} создан. Добавь предложение и подтверди.',reply_markup=trade_menu(tid,uid))
 try:await msg.get_bot().send_message(target,f'🤝 Игрок {uid} предложил трейд #{tid}.',reply_markup=trade_menu(tid,target))
 except TelegramError:await msg.reply_text('Не удалось написать игроку. Попроси его открыть бота через /start.')
async def trade_view(q,tid,uid):
 with db() as c:
  t=c.execute('SELECT * FROM trades WHERE id=?',(tid,)).fetchone()
  if not t or uid not in (t['a'],t['b']):return await q.answer('Трейд недоступен',show_alert=True)
  its=c.execute('SELECT ti.*,i.name,i.rarity FROM trade_items ti JOIN inventory i ON i.item_id=ti.item_id WHERE trade_id=?',(tid,)).fetchall()
 lines=[f'🤝 Трейд #{tid} · {t["status"]}',f'A {t["a"]}: {t["acoin"]} кило · подтверждение {t["aa"]}',f'B {t["b"]}: {t["bcoin"]} кило · подтверждение {t["ba"]}']
 lines += [f'#{i["item_id"]} {i["name"]} [{i["rarity"]}] от {i["owner_id"]}' for i in its] or ['Предметов пока нет']
 await q.answer();await q.message.reply_text('\n'.join(lines),reply_markup=trade_menu(tid,uid))
async def trade_coin(q,ctx,tid,uid):
 with db() as c:t=c.execute('SELECT * FROM trades WHERE id=? AND status="open"',(tid,)).fetchone()
 if not t or uid not in (t['a'],t['b']):return await q.answer('Трейд недоступен',show_alert=True)
 ctx.user_data['pending']={'type':'tradecoin','tid':tid};await q.answer();await q.message.reply_text('Введи число кило, которое предлагаешь (0 — убрать предложение).')
async def trade_item(q,tid,uid,kind):
 with db() as c:
  t=c.execute('SELECT * FROM trades WHERE id=? AND status="open"',(tid,)).fetchone();rows=c.execute('SELECT * FROM inventory WHERE owner_id=? AND kind=?',(uid,kind)).fetchall()
 if not t or uid not in (t['a'],t['b']):return await q.answer('Трейд недоступен',show_alert=True)
 if not rows:return await q.answer('Нет предметов такого типа',show_alert=True)
 await q.answer();await q.message.reply_text('Выбери предмет:',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f'#{r["item_id"]} {r["name"]}',callback_data=f'tadd:{tid}:{uid}:{r["item_id"]}')] for r in rows]))
async def trade_add(q,tid,uid,item):
 with db() as c:
  c.execute('BEGIN IMMEDIATE');t=c.execute('SELECT * FROM trades WHERE id=? AND status="open"',(tid,)).fetchone();it=c.execute('SELECT * FROM inventory WHERE item_id=? AND owner_id=?',(item,uid)).fetchone()
  if not t or uid not in (t['a'],t['b']) or not it:c.execute('ROLLBACK');return await q.answer('Предмет недоступен',show_alert=True)
  c.execute('INSERT OR IGNORE INTO trade_items VALUES(?,?,?)',(tid,item,uid));c.execute('UPDATE trades SET aa=0,ba=0 WHERE id=?',(tid,));c.execute('COMMIT')
 await q.answer('Добавлено');await trade_view(q,tid,uid)
 other=t['b'] if uid==t['a'] else t['a']
 try:await q.get_bot().send_message(other,f'🔔 Предложение в трейде #{tid} обновлено. Подтверди заново.',reply_markup=trade_menu(tid,other))
 except TelegramError:pass
async def trade_accept(q,tid,uid):
 with db() as c:
  c.execute('BEGIN IMMEDIATE');t=c.execute('SELECT * FROM trades WHERE id=?',(tid,)).fetchone()
  if not t or t['status']!='open' or uid not in (t['a'],t['b']):c.execute('ROLLBACK');return await q.answer('Трейд закрыт',show_alert=True)
  col='aa' if uid==t['a'] else 'ba';c.execute(f'UPDATE trades SET {col}=1 WHERE id=?',(tid,));t=c.execute('SELECT * FROM trades WHERE id=?',(tid,)).fetchone()
  if not (t['aa'] and t['ba']):c.execute('COMMIT');await q.answer('Подтверждено, ждём второго игрока.');return
  a=c.execute('SELECT balance FROM players WHERE user_id=?',(t['a'],)).fetchone();b=c.execute('SELECT balance FROM players WHERE user_id=?',(t['b'],)).fetchone();its=c.execute('SELECT * FROM trade_items WHERE trade_id=?',(tid,)).fetchall()
  if not a or not b or a['balance']<t['acoin'] or b['balance']<t['bcoin']:
   c.execute('UPDATE trades SET status="failed" WHERE id=?',(tid,));c.execute('COMMIT');return await q.answer('Недостаточно кило; сделка отменена.',show_alert=True)
  for i in its:
   own=c.execute('SELECT owner_id FROM inventory WHERE item_id=?',(i['item_id'],)).fetchone()
   if not own or own['owner_id']!=i['owner_id']:c.execute('UPDATE trades SET status="failed" WHERE id=?',(tid,));c.execute('COMMIT');return await q.answer('Предмет изменил владельца; сделка отменена.',show_alert=True)
  c.execute('UPDATE players SET balance=balance-?+? WHERE user_id=?',(t['acoin'],t['bcoin'],t['a']));c.execute('UPDATE players SET balance=balance-?+? WHERE user_id=?',(t['bcoin'],t['acoin'],t['b']))
  for i in its:c.execute('UPDATE inventory SET owner_id=? WHERE item_id=?',(t['b'] if i['owner_id']==t['a'] else t['a'],i['item_id']))
  c.execute('UPDATE trades SET status="completed" WHERE id=?',(tid,));c.execute('COMMIT')
 audit(uid,None,'trade_completed',tid);await q.answer('Трейд завершён!');await q.message.reply_text(f'✅ Трейд #{tid} завершён: кило и предметы переданы атомарно.')
 other=t['b'] if uid==t['a'] else t['a']
 try:await q.get_bot().send_message(other,f'✅ Трейд #{tid} завершён.')
 except TelegramError:pass
async def trade_decline(q,tid,uid):
 with db() as c:
  t=c.execute('SELECT * FROM trades WHERE id=? AND status="open"',(tid,)).fetchone()
  if not t or uid not in (t['a'],t['b']):return await q.answer('Трейд закрыт',show_alert=True)
  c.execute('UPDATE trades SET status="declined" WHERE id=?',(tid,))
 await q.answer('Трейд отклонён');await q.message.reply_text('❌ Сделка отклонена.')
async def admin_panel(msg,uid):
 if not admin(uid):return await msg.reply_text('⛔ Доступ запрещён.')
 await msg.reply_text('🔐 Закрытая админ-панель',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📊 Статистика',callback_data='admstats'),InlineKeyboardButton('🚨 Открытые трейды',callback_data='admtrades')],[InlineKeyboardButton('🛡 Белый список',callback_data='admwhite'),InlineKeyboardButton('📜 Журнал',callback_data='admlog')],[InlineKeyboardButton('➕ Выдать предмет/кило',callback_data='admgrant'),InlineKeyboardButton('🚫 Блокировка',callback_data='admblock')]]))
async def admin_cb(q,uid,data,ctx):
 if not admin(uid):return await q.answer('Доступ запрещён',show_alert=True)
 if data=='admstats':
  with db() as c:p=c.execute('SELECT COUNT(*) n,COALESCE(SUM(balance),0) b FROM players WHERE blocked=0').fetchone();i=c.execute('SELECT COUNT(*) n FROM inventory').fetchone()['n'];t=c.execute('SELECT COUNT(*) n FROM trades WHERE status="open"').fetchone()['n']
  await q.answer();return await q.message.reply_text(f'Игроков: {p["n"]}\nКило на балансах: {p["b"]:,}\nПредметов: {i}\nОткрытых трейдов: {t}')
 if data=='admtrades':
  with db() as c:rows=c.execute('SELECT * FROM trades WHERE status="open" ORDER BY created DESC LIMIT 20').fetchall()
  await q.answer();return await q.message.reply_text('\n'.join(f'#{r["id"]} {r["a"]} ↔ {r["b"]} · кило {r["acoin"]}/{r["bcoin"]} · подтверждения {r["aa"]}/{r["ba"]}' for r in rows) or 'Открытых трейдов нет.')
 if data=='admwhite':ctx.user_data['pending']={'type':'admintext'};await q.answer();return await q.message.reply_text('Введи: add ID или remove ID для белого списка.')
 if data=='admlog':
  with db() as c:rows=c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 15').fetchall()
  await q.answer();return await q.message.reply_text('\n'.join(f'#{r["id"]} {r["action"]} actor={r["actor"]} target={r["target"]} {r["details"]}' for r in rows)[:3900] or 'Журнал пуст.')
 if data=='admgrant':ctx.user_data['pending']={'type':'admintext'};await q.answer();return await q.message.reply_text('Команды: coins ID СУММА | premium ID | item ID artifact|weapon НОМЕР_ПРЕДМЕТА')
 if data=='admblock':ctx.user_data['pending']={'type':'admintext'};await q.answer();return await q.message.reply_text('Введи: block ID или unblock ID.')
async def admin_text(msg,uid,text):
 if not admin(uid):return await msg.reply_text('⛔ Доступ запрещён.')
 a=text.split()
 try:
  if len(a)==2 and a[0] in ('add','remove'):
   target=int(a[1])
   with db() as c:
    if a[0]=='add':c.execute('INSERT OR REPLACE INTO whitelist VALUES(?,?,?)',(target,uid,time.time()))
    else:c.execute('DELETE FROM whitelist WHERE user_id=?',(target,))
   audit(uid,target,'whitelist_'+a[0]);return await msg.reply_text(f'ID {target}: белый список обновлён.')
  if len(a)==2 and a[0] in ('block','unblock'):
   target=int(a[1])
   with db() as c:c.execute('UPDATE players SET blocked=? WHERE user_id=?',(a[0]=='block',target))
   audit(uid,target,'player_'+a[0]);return await msg.reply_text(f'ID {target}: {a[0]}.')
  if len(a)==3 and a[0]=='coins':
   target,amount=int(a[1]),int(a[2])
   if amount<1 or amount>10**18:raise ValueError()
   with db() as c:c.execute('UPDATE players SET balance=balance+? WHERE user_id=?',(amount,target))
   audit(uid,target,'admin_coins',amount);return await msg.reply_text(f'Выдано {amount:,} кило игроку {target}.')
  if len(a)==2 and a[0]=='premium':
   target=int(a[1])
   with db() as c:c.execute('UPDATE players SET premium_until=MAX(premium_until,?)+? WHERE user_id=?',(time.time(),10.5*86400,target))
   audit(uid,target,'admin_premium');return await msg.reply_text('Премиум выдан на 10 дней и 12 часов.')
  if len(a)==4 and a[0]=='item':
   target=int(a[1]);kind=a[2];ix=int(a[3]);it=ITEMS[kind][ix-1]
   if kind not in ITEMS or ix<1 or ix>len(ITEMS[kind]):raise ValueError()
   name,rarity,income,speed,steal,protect=it;exclusive=int('МИКРОФОН МАМКА-САМКА' in name)
   if exclusive and target not in ADMIN_IDS:return await msg.reply_text('Эксклюзивный микрофон можно выдать только ID из ADMIN_IDS.')
   with db() as c:c.execute('INSERT INTO inventory(owner_id,name,rarity,kind,income,speed,steal,protect,exclusive) VALUES(?,?,?,?,?,?,?,?,?)',(target,name,rarity,income,speed,steal,protect,exclusive))
   audit(uid,target,'admin_item',name);return await msg.reply_text(f'Выдано: {name} игроку {target}.')
 except (ValueError,IndexError,KeyError):return await msg.reply_text('Формат неверный. Проверь ID, сумму, тип и номер предмета.')
 await msg.reply_text('Команда не распознана.')
async def chess_challenge(msg,uid,target,stake):
 if uid==target or stake<1:return await msg.reply_text('Укажи другого игрока и ставку от 1 кило.')
 if not getp(target):return await msg.reply_text('Игрок должен сначала запустить бота.')
 with db() as c:
  c.execute('BEGIN IMMEDIATE');a=c.execute('SELECT balance FROM players WHERE user_id=?',(uid,)).fetchone();b=c.execute('SELECT balance FROM players WHERE user_id=?',(target,)).fetchone()
  if not a or not b or a['balance']<stake or b['balance']<stake:c.execute('ROLLBACK');return await msg.reply_text('У обоих игроков должен быть баланс не меньше ставки.')
  c.execute('UPDATE players SET balance=balance-? WHERE user_id=?',(stake,uid));cur=c.execute('INSERT INTO chess_games(w,b,stake,fen,status,created) VALUES(?,?,?,?,?,?)',(uid,target,stake,chess.Board().fen(),'pending',time.time()));gid=cur.lastrowid;c.execute('COMMIT')
 kb=InlineKeyboardMarkup([[InlineKeyboardButton('Принять шахматы',callback_data=f'chaccept:{gid}:{target}'),InlineKeyboardButton('Отклонить',callback_data=f'chdecline:{gid}:{target}')]])
 await msg.reply_text(f'♟ Матч #{gid}, ставка {stake:,} кило с каждого. Ставки зарезервированы.',reply_markup=kb)
 try:await msg.get_bot().send_message(target,f'♟ Игрок {uid} вызывает тебя на шахматы, ставка {stake:,} кило.',reply_markup=kb)
 except TelegramError:pass
async def chess_show(q,gid,uid):
 with db() as c:g=c.execute('SELECT * FROM chess_games WHERE id=?',(gid,)).fetchone()
 if not g or g['status']!='active' or uid not in (g['w'],g['b']):return await q.answer('Матч недоступен',show_alert=True)
 b=chess.Board(g['fen']);color=chess.WHITE if uid==g['w'] else chess.BLACK
 if b.turn!=color:return await q.answer('Сейчас ход другого игрока',show_alert=True)
 buttons=[]
 for rank in range(7,-1,-1):
  row=[]
  for file in range(8):
   sq=chess.square(file,rank);piece=b.piece_at(sq);label=piece.symbol() if piece else '·'
   row.append(InlineKeyboardButton(label,callback_data=f'chsq:{gid}:{uid}:{chess.square_name(sq)}'))
  buttons.append(row)
 buttons.append([InlineKeyboardButton('🔄 Обновить доску',callback_data=f'chboard:{gid}:{uid}')])
 await q.answer();await q.message.reply_text(f'♟ Матч #{gid}. Белые {g["w"]}; чёрные {g["b"]}. Выбери фигуру, затем клетку назначения. Пешка превращается в ферзя.',reply_markup=InlineKeyboardMarkup(buttons))
async def chess_square(q,ctx,gid,uid,sqname):
 with db() as c:g=c.execute('SELECT * FROM chess_games WHERE id=?',(gid,)).fetchone()
 if not g or g['status']!='active' or uid not in (g['w'],g['b']):return await q.answer('Матч недоступен',show_alert=True)
 b=chess.Board(g['fen']);color=chess.WHITE if uid==g['w'] else chess.BLACK
 if b.turn!=color:return await q.answer('Сейчас ход другого игрока',show_alert=True)
 key=f'chsel_{gid}';sel=ctx.user_data.get(key);sq=chess.parse_square(sqname)
 if not sel:
  p=b.piece_at(sq)
  if not p or p.color!=color:return await q.answer('Выбери свою фигуру',show_alert=True)
  ctx.user_data[key]=sqname;return await q.answer(f'Выбрано {sqname}; теперь выбери клетку назначения.')
 move=chess.Move(chess.parse_square(sel),sq);piece=b.piece_at(move.from_square)
 if piece and piece.piece_type==chess.PAWN and chess.square_rank(sq) in (0,7):move.promotion=chess.QUEEN
 ctx.user_data.pop(key,None)
 if move not in b.legal_moves:return await q.answer('Нелегальный ход. Выбери фигуру заново.',show_alert=True)
 b.push(move)
 with db() as c:c.execute('UPDATE chess_games SET fen=? WHERE id=? AND status="active"',(b.fen(),gid))
 await q.answer('Ход сделан')
 if b.is_game_over():await chess_finish(q.get_bot(),gid,b);return await q.message.reply_text(f'Матч завершён: {b.result()}.')
 await chess_show(q,gid,uid)
 with db() as c:g=c.execute('SELECT * FROM chess_games WHERE id=?',(gid,)).fetchone()
 nxt=g['w'] if b.turn==chess.WHITE else g['b']
 try:await q.get_bot().send_message(nxt,f'♟ Твой ход в матче #{gid}.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Открыть доску',callback_data=f'chboard:{gid}:{nxt}')]]))
 except TelegramError:pass
async def chess_finish(bot,gid,b):
 with db() as c:
  c.execute('BEGIN IMMEDIATE');g=c.execute('SELECT * FROM chess_games WHERE id=?',(gid,)).fetchone()
  if not g or g['status']!='active':c.execute('ROLLBACK');return
  winner=g['w'] if b.result()=='1-0' else g['b'] if b.result()=='0-1' else None
  if winner:c.execute('UPDATE players SET balance=balance+? WHERE user_id=?',(g['stake']*2,winner));c.execute('UPDATE stats SET wins=wins+1 WHERE user_id=?',(winner,))
  else:c.execute('UPDATE players SET balance=balance+? WHERE user_id IN (?,?)',(g['stake'],g['w'],g['b']))
  c.execute('UPDATE chess_games SET status="finished" WHERE id=?',(gid,));c.execute('COMMIT')
 for uid in (g['w'],g['b']):
  try:await bot.send_message(uid,f'♟ Матч #{gid}: {b.result()}. '+('Ставки возвращены при ничьей.' if not winner else f'Победитель {winner} получает банк.'))
  except TelegramError:pass
async def cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
 q=update.callback_query;uid=q.from_user.id;data=q.data or '';now=time.monotonic();key=f'anti_{uid}';arr=[t for t in ctx.application.bot_data.get(key,[]) if now-t<3]
 if len(arr)>=12:return await q.answer('❗ Не усердствуй, пирожочек! Подожди чуть-чуть.',show_alert=True)
 arr.append(now);ctx.application.bot_data[key]=arr
 if not getp(uid):ensure(q.from_user)
 if locked(uid):return await q.answer('⛔ Доступ ограничен',show_alert=True)
 if data=='menu':await q.answer();return await q.message.reply_text('Главное меню',reply_markup=menu())
 if data=='factory':await q.answer();return await factory_msg(q.message,uid)
 if data=='profile':await q.answer();return await profile_msg(q.message,uid)
 if data=='collect':await q.answer();return await collect_msg(q.message,uid)
 if data=='upgrade':await q.answer();return await upgrade_msg(q.message,uid)
 if data=='inventory':await q.answer();return await inventory_msg(q.message,uid)
 if data=='tops':await q.answer();return await tops_msg(q.message)
 if data=='games':await q.answer();return await games_msg(q.message)
 if data=='tradehelp':await q.answer();return await q.message.reply_text('Создать трейд: /trade ID. Кило и предметы добавляются через кнопки в личных сообщениях.')
 if data=='promohelp':await q.answer();return await q.message.reply_text('Активируй код командой /promo КОД. Секретные коды не публикуются в меню.')
 if data=='premium':await q.answer();return await premium_msg(q.message)
 if data=='buypremium':return await buy_premium(update,ctx)
 if data in ('rulka','dice'):
  ctx.user_data['pending']={'type':'bet','game':data};await q.answer();return await q.message.reply_text('Введи ставку в кило (целое число, не больше твоего баланса).')
 if data=='chesshelp':await q.answer();return await q.message.reply_text('Создать шахматный матч: /chess ID СТАВКА. Пока матч не завершён, ставки зарезервированы.')
 if data.startswith('tview:'):
  _,tid,who=data.split(':');return await trade_view(q,int(tid),int(who))
 if data.startswith('tcoin:'):
  _,tid,who=data.split(':');return await trade_coin(q,ctx,int(tid),int(who))
 if data.startswith('titem:'):
  _,tid,who,kind=data.split(':');return await trade_item(q,int(tid),int(who),kind)
 if data.startswith('tadd:'):
  _,tid,who,item=data.split(':');return await trade_add(q,int(tid),int(who),int(item))
 if data.startswith('taccept:'):
  _,tid,who=data.split(':');return await trade_accept(q,int(tid),int(who))
 if data.startswith('tdecline:'):
  _,tid,who=data.split(':');return await trade_decline(q,int(tid),int(who))
 if data.startswith('adm') :return await admin_cb(q,uid,data,ctx)
 if data.startswith('chaccept:'):
  _,gid,who=data.split(':');gid=int(gid);who=int(who)
  if uid!=who:return await q.answer('Только приглашённый игрок может ответить',show_alert=True)
  with db() as c:
   c.execute('BEGIN IMMEDIATE');g=c.execute('SELECT * FROM chess_games WHERE id=? AND status="pending"',(gid,)).fetchone();p=c.execute('SELECT balance FROM players WHERE user_id=?',(uid,)).fetchone()
   if not g or not p:c.execute('ROLLBACK');return await q.answer('Матч уже закрыт',show_alert=True)
   if time.time()-g['created']>600:
    c.execute('UPDATE players SET balance=balance+? WHERE user_id=?',(g['stake'],g['w']));c.execute('UPDATE chess_games SET status="expired" WHERE id=?',(gid,));c.execute('COMMIT');return await q.answer('Вызов истёк через 10 минут; ставка возвращена.',show_alert=True)
   if p['balance']<g['stake']:
    c.execute('UPDATE players SET balance=balance+? WHERE user_id=?',(g['stake'],g['w']));c.execute('UPDATE chess_games SET status="failed" WHERE id=?',(gid,));c.execute('COMMIT');return await q.answer('У тебя не хватает кило; вызов отменён.',show_alert=True)
   c.execute('UPDATE players SET balance=balance-? WHERE user_id=?',(g['stake'],uid));c.execute('UPDATE chess_games SET status="active" WHERE id=?',(gid,));g=c.execute('SELECT * FROM chess_games WHERE id=?',(gid,)).fetchone();c.execute('COMMIT')
  await q.answer('Матч начался');await chess_show(q,gid,uid)
  try:await q.get_bot().send_message(g['w'],f'♟ Матч #{gid} принят. Твой ход белыми.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Открыть доску',callback_data=f'chboard:{gid}:{g["w"]}')]]))
  except TelegramError:pass
  return
 if data.startswith('chdecline:'):
  _,gid,who=data.split(':');gid=int(gid);who=int(who)
  with db() as c:
   g=c.execute('SELECT * FROM chess_games WHERE id=? AND status="pending"',(gid,)).fetchone()
   if g and uid==who:c.execute('UPDATE players SET balance=balance+? WHERE user_id=?',(g['stake'],g['w']));c.execute('UPDATE chess_games SET status="declined" WHERE id=?',(gid,))
  return await q.answer('Матч отклонён, ставки возвращены.')
 if data.startswith('chboard:'):
  _,gid,who=data.split(':');return await chess_show(q,int(gid),int(who))
 if data.startswith('chsq:'):
  _,gid,who,sq=data.split(':');return await chess_square(q,ctx,int(gid),int(who),sq)
 if data.startswith('risk:'):
  _,step=data.split(':');return await rulka_step(q,uid,int(step),ctx)
 if data.startswith('cashout:'):
  _,step=data.split(':');state=ctx.user_data.get('rulka')
  if not state:return await q.answer('Игра завершена',show_alert=True)
  payout=int(state['bet']*state['mult']);ctx.user_data.pop('rulka',None)
  with db() as c:c.execute('UPDATE players SET balance=balance+? WHERE user_id=?',(payout,uid))
  await q.answer('Забрано!');return await q.message.reply_text(f'🐖 Ты забрала {payout:,} кило с множителем ×{state["mult"]}.')
 await q.answer('Неизвестное действие')
async def rulka_step(q,uid,step,ctx):
 s=ctx.user_data.get('rulka')
 if not s or s['step']!=step:return await q.answer('Эта попытка уже использована.',show_alert=True)
 risks=[.25,.38,.52,.68,.82,.99];mults=[1.25,1.7,2.4,3.5,5.5,10.0]
 if random.random()<risks[step]:
  ctx.user_data.pop('rulka',None);await q.answer('Не повезло!');return await q.message.reply_text(f'💥 Рулька подвела на шаге {step+1}/6. Ставка {s["bet"]:,} кило потеряна.')
 s['step']=step+1;s['mult']=mults[step]
 if s['step']>=6:
  payout=s['bet']*10;ctx.user_data.pop('rulka',None)
  with db() as c:c.execute('UPDATE players SET balance=balance+? WHERE user_id=?',(payout,uid))
  await q.answer('Невероятно!');return await q.message.reply_text(f'🐖 Ты прошла все шесть шагов! Выплата ×10: {payout:,} кило.')
 kb=InlineKeyboardMarkup([[InlineKeyboardButton('⚠️ Рискнуть ещё',callback_data=f'risk:{s["step"]}'),InlineKeyboardButton('💰 Забрать выигрыш',callback_data=f'cashout:{s["step"]}')]])
 await q.answer('Успех!');await q.message.reply_text(f'Успешный шаг {s["step"]}/6. Текущий множитель ×{s["mult"]}. Продолжить или забрать?',reply_markup=kb)

async def text_handler(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
 msg=update.effective_message;u=update.effective_user;uid=u.id;text=msg.text or '';ensure(u)
 if locked(uid):return await msg.reply_text('⛔ Доступ ограничен.')
 aliases={'🏭 Завод':'factory','👤 Профиль':'profile','📦 Собрать кило':'collect','⬆️ Улучшить':'upgrade','🎒 Инвентарь':'inventory','🏆 Топы':'tops','🎲 Игры':'games','🤝 Трейды':'tradehelp'}
 if text in aliases:
  action=aliases[text]
  if action=='factory':return await factory_msg(msg,uid)
  if action=='profile':return await profile_msg(msg,uid)
  if action=='collect':return await collect_msg(msg,uid)
  if action=='upgrade':return await upgrade_msg(msg,uid)
  if action=='inventory':return await inventory_msg(msg,uid)
  if action=='tops':return await tops_msg(msg)
  if action=='games':return await games_msg(msg)
  return await msg.reply_text('Создать трейд: /trade ID')
 pending=ctx.user_data.get('pending')
 if not pending:return await msg.reply_text('Используй /start, кнопки меню или /help.')
 typ=pending.get('type')
 if typ=='tradecoin':
  try:amount=int(text.strip())
  except ValueError:return await msg.reply_text('Введи целое число.')
  if amount<0 or amount>10**18:return await msg.reply_text('Недопустимая сумма.')
  tid=pending['tid']
  with db() as c:
   c.execute('BEGIN IMMEDIATE');t=c.execute('SELECT * FROM trades WHERE id=? AND status="open"',(tid,)).fetchone();p=c.execute('SELECT balance FROM players WHERE user_id=?',(uid,)).fetchone()
   if not t or uid not in (t['a'],t['b']) or not p or p['balance']<amount:c.execute('ROLLBACK');return await msg.reply_text('Трейд закрыт или недостаточно кило.')
   col='acoin' if uid==t['a'] else 'bcoin';c.execute(f'UPDATE trades SET {col}=?,aa=0,ba=0 WHERE id=?',(amount,tid));c.execute('COMMIT')
  ctx.user_data.pop('pending',None);await msg.reply_text(f'Предложение в трейде #{tid}: {amount:,} кило.',reply_markup=trade_menu(tid,uid));return
 if typ=='bet':
  try:bet=int(text.strip())
  except ValueError:return await msg.reply_text('Введи ставку целым числом.')
  p=getp(uid)
  if bet<1 or bet>p['balance']:return await msg.reply_text('Ставка должна быть положительной и не превышать баланс.')
  game=pending['game'];ctx.user_data.pop('pending',None)
  with db() as c:
   c.execute('BEGIN IMMEDIATE');p=c.execute('SELECT balance FROM players WHERE user_id=?',(uid,)).fetchone()
   if not p or p['balance']<bet:c.execute('ROLLBACK');return await msg.reply_text('Баланс изменился, повтори попытку.')
   c.execute('UPDATE players SET balance=balance-? WHERE user_id=?',(bet,uid));c.execute('COMMIT')
  if game=='dice':
   dice=await ctx.bot.send_dice(msg.chat_id,emoji='🎲');v=dice.dice.value;prize=bet*2 if v==1 else 0
   with db() as c:c.execute('UPDATE players SET balance=balance+? WHERE user_id=?',(prize,uid))
   return await msg.reply_text(f'🎲 Выпало {v}. '+(f'Победа, выплата {prize:,} кило.' if prize else f'Ставка {bet:,} кило проиграна.'))
  ctx.user_data['rulka']={'bet':bet,'step':0,'mult':1.0}
  return await msg.reply_text('🐖 Первый шаг: риск 25%, множитель при успехе ×1,25.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⚠️ Рискнуть',callback_data='risk:0')]]))
 if typ=='admintext' and admin(uid):ctx.user_data.pop('pending',None);return await admin_text(msg,uid,text)
 if typ=='renamefactory':
  name=text.strip()[:60]
  if not name:return await msg.reply_text('Название не может быть пустым.')
  with db() as c:c.execute('UPDATE players SET factory_name=? WHERE user_id=?',(name,uid))
  ctx.user_data.pop('pending',None);return await msg.reply_text(f'🏭 Завод теперь называется «{name}».')
 if typ=='renamenick':
  name=text.strip()[:32]
  if not name:return await msg.reply_text('Ник не может быть пустым.')
  with db() as c:c.execute('UPDATE players SET nick=? WHERE user_id=?',(name,uid))
  ctx.user_data.pop('pending',None);return await msg.reply_text(f'Ник изменён: {name}.')
async def help_cmd(update,ctx):
 await update.effective_message.reply_text('Команды:\n/start /help /factory /profile /collect /upgrade /inventory /tops\n/promo КОД\n/trade ID\n/fuckit ID СУММА (или ответом на сообщение /fuckit СУММА)\n/chess ID СТАВКА\n/renamefactory /renamenick /premium /games /admin\nЗавод производит непрерывно и заполняется за 6 часов. Кража — раз в час. Админ-доступ только по ADMIN_IDS.')
async def cmd_factory(u,c):await factory_msg(u.effective_message,u.effective_user.id)
async def cmd_profile(u,c):await profile_msg(u.effective_message,u.effective_user.id)
async def cmd_collect(u,c):await collect_msg(u.effective_message,u.effective_user.id)
async def cmd_upgrade(u,c):await upgrade_msg(u.effective_message,u.effective_user.id)
async def cmd_inventory(u,c):await inventory_msg(u.effective_message,u.effective_user.id)
async def cmd_tops(u,c):await tops_msg(u.effective_message)
async def cmd_promo(u,c):await promo_msg(u.effective_message,u.effective_user.id,' '.join(c.args))
async def cmd_trade(u,c):
 if c.args and c.args[0].isdigit():return await create_trade(u.effective_message,u.effective_user.id,int(c.args[0]))
 reply=u.effective_message.reply_to_message
 if reply and reply.from_user:return await create_trade(u.effective_message,u.effective_user.id,reply.from_user.id)
 return await u.effective_message.reply_text('Использование: /trade ID или ответом на сообщение игрока командой /trade.')
async def cmd_theft(u,c):
 if u.effective_message.reply_to_message and u.effective_message.reply_to_message.from_user:
  target=u.effective_message.reply_to_message.from_user.id;amount=int(c.args[0]) if c.args and c.args[0].isdigit() else 100
 elif len(c.args)>=2 and c.args[0].isdigit() and c.args[1].isdigit():target,amount=int(c.args[0]),int(c.args[1])
 else:return await u.effective_message.reply_text('Использование: /fuckit ID СУММА или ответом: /fuckit СУММА')
 await theft(u.effective_message,u.effective_user.id,target,amount)
async def cmd_chess(u,c):
 if len(c.args)<2 or not c.args[0].isdigit() or not c.args[1].isdigit():return await u.effective_message.reply_text('Использование: /chess ID СТАВКА')
 await chess_challenge(u.effective_message,u.effective_user.id,int(c.args[0]),int(c.args[1]))
async def cmd_admin(u,c):await admin_panel(u.effective_message,u.effective_user.id)
async def cmd_renamefactory(u,c):c.user_data['pending']={'type':'renamefactory'};await u.effective_message.reply_text('Введи новое название завода (до 60 символов).')
async def cmd_renamenick(u,c):c.user_data['pending']={'type':'renamenick'};await u.effective_message.reply_text('Введи новый ник (до 32 символов).')
async def cmd_premium(u,c):await premium_msg(u.effective_message)
async def cmd_games(u,c):await games_msg(u.effective_message)
async def err(update,ctx):
 log.exception('Unhandled error',exc_info=ctx.error)
 if update and update.effective_message:
  try:await update.effective_message.reply_text('⚠️ Ошибка. Попробуй ещё раз чуть позже.')
  except TelegramError:pass
def main():
 init_db();app=Application.builder().token(TOKEN).build()
 handlers={'start':start,'help':help_cmd,'factory':cmd_factory,'profile':cmd_profile,'collect':cmd_collect,'upgrade':cmd_upgrade,'inventory':cmd_inventory,'tops':cmd_tops,'promo':cmd_promo,'trade':cmd_trade,'fuckit':cmd_theft,'chess':cmd_chess,'admin':cmd_admin,'renamefactory':cmd_renamefactory,'renamenick':cmd_renamenick,'premium':cmd_premium,'games':cmd_games}
 for name,fn in handlers.items():app.add_handler(CommandHandler(name,fn))
 app.add_handler(PreCheckoutQueryHandler(precheckout));app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT,paid));app.add_handler(CallbackQueryHandler(cb));app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,text_handler));app.add_error_handler(err)
 app.run_webhook(listen='0.0.0.0',port=PORT,url_path=TOKEN,webhook_url=f'{WEBHOOK_URL}/{TOKEN}',drop_pending_updates=True)
if __name__=='__main__':main()
