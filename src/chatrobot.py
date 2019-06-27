# -*- coding:utf-8 -*-

import sys
import itchat
import logging
import threading
import collections
import re


context = threading.local()
context.msg = None

msg = context.msg


class ChatRobot:
    nick_name = "chatrobot"
    userName = ""

    def __init__(self, conf=None):
        """
        init methods.
            initialize listen rule, there are three element in it, `onechat`, `groupchat` and
            `mechat`, onechat means private chat, groupchat means a chatroom, mechat means self
            word content.All the rules defined will store in this dict, and in order to reduce 
            code logic to set these three value as defaultdict.

            login wechat client.it set hotReload as True, so you can login without scan QR image
            agin and agin.

            get your information such as nick_name and userName, nick name is different from username
            refer from itchat document and itchat support using username to search user information.

            initialize logger module.chatbot use python `logging` module to note the important data.

            initialize chat context.Chat context store the message object and it's relative independence
            in different threading.
        """
        # listen_rule
        # store your listen rules
        # you can add new rule by using `listen` methods or `add_listen_rule` method
        self.listen_rule = {
            "onechat": collections.defaultdict(list),
            "groupchat": collections.defaultdict(list),
            "mechat": collections.defaultdict(list)
        }

        # login to wechat client
        if conf is not None:
            login_conf = conf.get('login_conf', {})
        else:
            login_conf = {}
        hot_reload = login_conf.get('hotReload', False)
        status_storage_dir = login_conf.get('statusStorageDir', 'chatbot.pkl')
        enable_cmd_qr = login_conf.get('enableCmdQR', False)
        pic_dir = login_conf.get('picDir', None)
        qr_callback = login_conf.get('qr_callback', None)
        login_callback = login_conf.get('loginCallback', None)
        exit_callback = login_conf.get('exitCallback', None)
        itchat.auto_login(
            hotReload=hot_reload,
            statusStorageDir=status_storage_dir,
            enableCmdQR=enable_cmd_qr,
            picDir=pic_dir,
            qrCallback=qr_callback,
            loginCallback=login_callback,
            exitCallback=exit_callback)

        # initialize self information
        # itchat provide `search_friends` methods to search user information by user name
        # if no user name support it return your own infomation, it is useful so save it.
        me = itchat.search_friends()
        self.nick_name = me['nick_name']
        self.userName = me['UserName']

        # initialize logger module
        # it's important to log while the program is running, chatbot use logging module to
        # log the important data, and it send to stout device
        # TODO: log configurable
        if conf is not None:
            logger_conf = conf.get('logger_conf', {})
        else:
            logger_conf = {}
        level = logger_conf.get('level', 'DEBUG')
        log_format = logger_conf.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        name = logger_conf.get('name', __name__)
        path = logger_conf.get('path', None)

        if level.upper() == "INFO":
            level = logging.INFO
        elif level.upper() == "WARNING":
            level = logging.WARNING
        elif level.upper() == "ERROR":
            level = logging.ERROR
        elif level.upper() == "FATAL":
            level = logging.FATAL
        else:
            level = logging.DEBUG

        logging.basicConfig(level=level, format=log_format, filename=path)
        self.logger = logging.getLogger(name)

    def add_listen_rule(self, key_word, handler, is_one=True, is_self=False, is_group=False, is_at=False, nick_name=None):
        """
        add_listen_rule
            add a listen rule to chatbot.
        """
        listen_rule = self.listen_rule

        rules_box = []
        if is_self:
            rules_box.append(listen_rule["mechat"])
        if is_group:
            rules_box.append(listen_rule["groupchat"])
        if is_one:
            rules_box.append(listen_rule["onechat"])

        for rules in rules_box:
            rule = {
                "handler": handler,
                "handlerName": handler.__name__,
                "is_at": is_at
            }
            if nick_name is not None:
                rule['nick_name'] = nick_name
            rules[key_word].append(rule)

    def listen(self, key_word, is_one=False, is_self=False, is_group=False, is_at=False, nick_name=None):
        """
        add listen rule by decorator
        """
        if not is_one and not is_self and not is_group:
            is_one = True

        def decorator(f):
            self.add_listen_rule(key_word, f, is_one, is_self, is_group, is_at, nick_name)
            return f

        return decorator

    @staticmethod
    def get_from_username(msg, is_group_chat=False):
        """
        get msg sender nick_name
        """
        if is_group_chat:
            return msg['Actualnick_name'].encode()

        friend = itchat.search_friends(userName=msg["from_user_name"])
        if friend is None:
            return "未知"
        else:
            return friend['nick_name']

    def get_group_selfname(self, msg):
        """
        get your nick_name in a centain group
        """
        if msg.get('User').has_key('Self') and msg['User']['Self']['DisplayName'].encode() != '':
            return msg['User']['Self']['DisplayName'].encode()
        else:
            return self.nick_name

    def _get_rules(self):
        """
        get the rules base on context.
        """
        global context
        msg = context.msg

        text = msg["Text"].encode()
        if context.is_at:
            prefix = '@' + self.get_group_selfname(msg) + ' '
            text = text.replace(prefix, '')
        self.logger.debug('关键词: ({})'.format(text))

        rules = []
        aim_rules = None
        if context.from_user_nick_name == self.nick_name:
            self.logger.debug('检索个人规则词表')
            aim_rules = self.listen_rule['mechat']
        elif context.is_group_chat:
            self.logger.debug('检索群聊规则词表')
            aim_rules = self.listen_rule["groupchat"]
        else:
            self.logger.debug('检索私聊规则词表')
            aim_rules = self.listen_rule["onechat"]

        for key, value in aim_rules.items():
            key_com = re.compile(key)
            if sys.version_info.major < 3 and key_com.match(text):
                rules.extend(value)
            elif sys.version_info.major == 3 and key_com.match(text.decode()):
                rules.extend(value)
        return rules

    def _handler_one_rule(self, rule):
        """
        running a handler rule
        """
        self.logger.info("触发处理函数: {}".format(rule['handlerName']))
        global context
        msg = context.msg

        if not context.is_group_chat:
            rule['is_at'] = False

        if rule['is_at'] == context.is_at and rule.get('nick_name', context.from_user_nick_name) == context.from_user_nick_name:
            handler = rule['handler']
            content = handler()

            if type(content) == type(str()):
                self.logger.debug("返回信息: {}".format(content))
                msg.User.send(content)
            elif type(content) == type(tuple()):
                t, arg = content
                if t == "text":
                    self.logger.debug("返回信息: {}".format(arg))
                    msg.User.send(arg)
                elif t == "image":
                    self.logger.debug("返回图片: {}".format(arg))
                    msg.User.send_image(arg)
                else:
                    self.logger.debug("未支持返回类型: {}".format(t))
            else:
                self.logger.warning("处理函数返回格式错误，错误类型: {}".format(str(type(content))))
        else:
            self.logger.info("处理函数配置项匹配失败")
            if rule['is_at'] != context.is_at:
                self.logger.debug("群聊@属性不匹配")
                self.logger.debug("{} != {}".format(str(rule['is_at']), str(context.is_at)))
            if rule.get('nick_name', context.from_user_nick_name) != context.from_user_nick_name:
                self.logger.debug("对象昵称不匹配")
                self.logger.debug(
                    "{} != {}".format(rule.get('nick_name', context.from_user_nick_name), context.from_user_nick_name))

    def _handler_diliver(self, msg, is_group_chat):
        """
        while msg is comming, check it and return
        """
        global context
        context.msg = msg
        context.is_group_chat = is_group_chat
        context.is_at = msg.get('is_at', False)
        context.from_user_nick_name = self.get_from_username(msg)

        rules = self._get_rules()

        self.logger.info("触发规则: {} 条".format(len(rules)))

        for rule in rules:
            self._handler_one_rule(rule)

    def run(self):
        """
        run chatbot
        """

        @itchat.msg_register(itchat.content.TEXT)
        def trigger_chatone(msg):
            from_user_name = self.get_from_username(msg)
            text = msg['Text'].encode()
            self.logger.info('(普通消息){}: {}'.format(from_user_name, text))

            t = threading.Thread(target=self._handler_diliver, args=(msg, False))
            t.setDaemon(True)
            t.start()

        @itchat.msg_register(itchat.content.TEXT, is_group_chat=True)
        def trigger_chatgroup(msg):
            from_user_name = self.get_from_username(msg, is_group_chat=True)
            text = msg['Text'].encode()
            self.logger.info('(群消息){}: {}'.format(from_user_name, text))

            t = threading.Thread(target=self._handler_diliver, args=(msg, True))
            t.setDaemon(True)
            t.start()

        itchat.run()
