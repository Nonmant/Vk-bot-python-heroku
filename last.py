from multiprocessing import Process, Pipe, Pool
import requests
import json
import time

from socket import gaierror
from sys import stdout, stderr

#function to download files from dropbox
def downloadDropbox(dataIn, downloadHeaders):
    try:
        dropboxDownl=requests.post('https://content.dropboxapi.com/2/files/download',headers=downloadHeaders)
    except requests.exceptions.RequestException as e:
        print('error in dropboxDownl:', e)
    else:
        if not dropboxDownl.status_code==200:
            print('error: dropboxDownl.status_code:', dropboxDownl.status_code)
        else:
            try:
                dataOut=dropboxDownl.json()
                print('data from dropbox has been downloaded successfully')
                return dataOut
            except ValueError as e:
                print('error in json.decode dropboxDownl.json',e)
    print('local data has been used instead')
    return dataIn

#function to upload files to dropbox
def uploadDropbox(dataIn, uploadHeaders):
    try:
        dropboxUpl=requests.post('https://content.dropboxapi.com/2/files/upload', data=str(dataIn).replace("'", '\"').encode('utf8'), headers=uploadHeaders)
    except requests.exceptions.RequestException as e:
        print('error in dropboxUpl:', e)
    else:
        if not dropboxUpl.status_code==200:
            print('error: dropboxUpl.status_code:',dropboxUpl.status_code)
        else:
            try:
                dropboxUplAns=dropboxUpl.json()
                if "id" in dropboxUplAns:
                    print('data has been uploaded to dropbox successfully')
                else:
                    print('something gone wrong with uploading data to dropbox: ', str(dropboxUplAns))
            except ValueError as e:
                print('error in json.decode dropboxUpl.json',e)

#function to set every header value type to str
def jsonToHeaders(jsonIn):
    jsonOut=jsonIn.copy()
    for key,val in jsonOut.items():
        if not type(val) is str:
            jsonOut[key]=str(jsonIn[key]).replace("'",'\"')
    return jsonOut

#function to send vk message
def answer(text, id, token, attaches=''):#return -1: answer isn't correct, !=-1: message id
    messageSendParams={"message":text,
                       "user_id":id,
                       "access_token":token,
                       "v" : 5.69,
                       "attachment":attaches}
    messageSend=requests.get('https://api.vk.com/method/messages.send',
                             params=messageSendParams)
    if not messageSend.status_code==200:
        print('err: messageSend.status_code=',
              messageSend.status_code)
        return -1
    if "response" in messageSend.json():
        print('answered:', messageSend.json()["response"])
        return messageSend.json()["response"]
    return -1

class KillerCallbackEventHandler:
        """Stops CallbackEventHandler on any 'sig-' signals"""
        def __init__(self):
            for i in [x for x in dir(signal) if x.startswith("SIG")]:
                try:
                    signum = getattr(signal,i)
                    signal.signal(signum,self.kill)
                except (OSError, RuntimeError, ValueError): #OSError for Python3, RuntimeError for 2
                    continue

        def kill(self, signum, frame):
            print('closing Callback event handler with killer')
            #uploadDropbox(self.proxies, self.headers)
            quit()

def callbackBot1(pipe):
    path="Bot1"
    print('callbackEventHandlerFunc ', path, ' have pipe: ', str(pipe))

    with open(path+'/callback.json') as data_file:
        callbackParams = json.load(data_file)
        access_token=callbackParams["access_token"]

    with open(path+'/dropboxUpl.json')as data_file:
        proxyDropboxUplHeaders = jsonToHeaders(json.load(data_file))

    with open(path+'/dropboxDownl.json')as data_file:
        proxyDropboxDownlHeaders = jsonToHeaders(json.load(data_file))

    with open(path+'/Bot1.json') as data_file:
        params=json.load(data_file)

    params=downloadDropbox(params, proxyDropboxDownlHeaders)

    processKiller=KillerCallbackEventHandler()

    prevSec=0
    secToSleep=0
    messagesIgnore=[]
    adminId=0

    while True:
#if nothing to receive
        if not pipe.poll():
            curSec=time.time()

            if curSec-prevSec>1:
                secToSleep+=curSec-prevSec
                prevSec=curSec

            if secToSleep>0:
        #if nothing to do
                secSpend=time.time()-curSec
                time.sleep(min([max([secToSleep-secSpend,0]),3]))

        while pipe.poll():
            secToSleep=1
            prevSec=time.time()
            message=pipe.recv()
            print('received event ', str(message))

            if message=="stop":
                print('killing eventHandlerProc')
                return 0
            if message["type"]=="group_join":
                userId=message["object"]["user_id"]
                messageAnsId=answer(params["messages"]["newSubscriber"],userId, access_token)
                if messageAnsId!=-1:
                    messagesIgnore.append(messageAnsId)
                continue

            if message["type"]=="message_new":
                message=message["object"]

                userId=message["user_id"]
                messageId=message["id"]

                if not (userId and messageId):
                    continue

                if messageId in messagesIgnore:
                    print('ignoring message id', str(messageId))
                    continue

                messagesIgnore.append(messageId)

                messageText=message["body"]

                messageReadParams={"start_message_id":messageId, "peer_id":userId, "access_token":access_token, "v" : 5.69}
                messageRead=requests.get('https://api.vk.com/method/messages.markAsRead',
                                        params=messageReadParams,
                                        timeout=10)
                print('messageRead.json:', messageRead.json())

                if messageText.find(params["key_phrase"])!=-1:
                    messageAnsId=answer(params["messages"]["adminGreeting"],userId, access_token)
                    if messageAnsId!=-1:
                        messagesIgnore.append(messageAnsId)
                    adminId=userId

                if userId==adminId:
                    for key in params["adminKeys"]:
                        i=messageText.find(key)
                        if i==-1:
                            continue
                        adminId=0
                        if key == '0-':
                            messageAnsId=answer(params["messages"]["newSubscriber"],userId, access_token)
                            if messageAnsId!=-1:
                                messagesIgnore.append(messageAnsId)
                        elif key == '1-':
                            params["messages"]["newSubscriber"]=messageText[messageText.index(key)+len(key):]

                            messageAnsId=answer(params["messages"][key]+params["messages"]["newSubscriber"],userId, access_token)
                            if messageAnsId!=-1:
                                messagesIgnore.append(messageAnsId)
                            uploadDropbox(params, proxyDropboxUplHeaders)
                continue

class BotPar(object):
    """BotPar class, that holds 2 pipelines and name for bot instance"""
    def __init__(self, name, pipS, pipR):
        self.name=name
        self.pipR=pipR
        self.pipS=pipS

botPars=[]
#web app for heroku
globalCallbackParams={}
globalPipSBot1=[]
globalPipRBot1=[]

import signal

if __name__ == "__main__":
    def setGlobals():
        global botPars

        global globalPipSBot1
        global globalPipRBot1
        global globalCallbackParams

        with open('Bot1/callback.json') as data_file:
            globalCallbackParams["Bot1"] = json.load(data_file)

        globalPipRBot1, globalPipSBot1=Pipe(False)
        eventHandlerProcBot1=Process(target=callbackBot1, name="callback Event Handler Bot1",
                                args=(globalPipRBot1,))
        eventHandlerProcBot1.start()
        botPars=[BotPar("Bot1",globalPipSBot1,globalPipRBot1)]

    setGlobals()

    with open('favicon.ico', "rb") as data_file:
        favicon = data_file.read()
    with open('robots.txt', "r") as data_file:
        robots = data_file.read()

    import web
    urls = ('/(.*)', 'hello')

    class hello:
        def GET(self, name):
            if name=='favicon.ico':
                web.header('Content-Type', 'image/x-icon')
                return favicon
            elif name=='robots.txt':
                return robots
            return 'Hope, vk bot would work now'

        def POST(self, name):

            global botPars
        #global globalPipR
        #global globalCallbackParams

            #print('global params:', str(globalCallbackParams), ', pipS:', str(globalPipS))

            if not web.data():
                print('WARNING: no data in post-request')
                return('Post, no data')
            try:
                data = json.loads(web.data())
            except ValueError:
                print("Error in hello post json.loads, data:", data)
                return 'Post, wrong data'

            for botPar in botPars:
                par=globalCallbackParams[botPar.name]
                if par["group_id"]==data["group_id"]:

                    if data["type"]=="confirmation":
                        print("confirmation for group ", str(par["group_id"]))
                        return par["conf answer"]

                    if not "secret" in data:
                        return "No 'secret' in json"

                    if not par["secret"]==data["secret"]:
                        return "Wrong secret"

                    if not "type" in data:
                        print('WARNING: no type in json in post-request')
                        return "No 'type' in json"

                    botPar.pipS.send(data)
                    break
            else:
                return "No correct bot"

            return "ok"#defaul answer

    #print(globals())
    app = web.application(urls, globals())

    class Killer:
        """Stops all on signint or signterm signals"""
        def __init__(self, webapp):
            for i in [x for x in dir(signal) if x.startswith("SIG")]:
                try:
                    signum = getattr(signal,i)
                    signal.signal(signum,self.kill)
                except (OSError, RuntimeError, ValueError): #OSError for Python3, RuntimeError for 2
                    continue
            #signal.signal(signal.SIGINT, self.kill)
            #signal.signal(signal.SIGTERM, self.kill)
            self.webapp=webapp

        def kill(self, signum, frame):
            print('closing all with killer')
            global botPars
            for botPar in botPars:
                botPar.pipS.send("stop")
            '''
            try:
                self.webapp.stop()
            except AttributeError:
                print('webapp already closed')'''
            print('all closed')
            quit()

    killerObj = Killer(app)

    app.run()#port=8888
