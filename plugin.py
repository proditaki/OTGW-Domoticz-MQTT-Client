"""
<plugin key="OTGWMqttClient" name="OTGW MqttClient" version="0.0.3">
    <params>
        <param field="Address" label="MQTT Server address" width="300px" required="true" default="127.0.0.1"/>
        <param field="Port" label="MQTT Server Port" width="300px" required="true" default="1883"/>
        <param field="Mode1" label="OTGW Server address" width="300px" required="true" default="192.168.2.6"/>
        <param field="Mode2" label="discovery topic" width="300px" required="true" default="homeassistant"/>
        <param field="Mode3" label="OTGW topic" width="300px" required="true" default="OTGW"/>
    </params>
</plugin>
"""
import Domoticz
import json
import os
import time
from requests import get
from requests import post

from datetime import datetime
from itertools import count, filterfalse

import re
import traceback

from mqtt import MqttClientSH2


class BasePlugin:
    # MQTT settings
    mqttClient = None

    def __init__(self):
        return

    def onStart(self):
        self.base_topic = Parameters['Mode2'].strip()
        self.otgw_topic = Parameters['Mode3'].strip()
        self.otgwserveraddress = Parameters['Mode1'].strip()
        self.mqttserveraddress = Parameters['Address'].strip()
        self.mqttserverport = Parameters['Port'].strip()

        self.mqttClient = MqttClientSH2(self.mqttserveraddress, self.mqttserverport, "", self.onMQTTConnected, self.onMQTTDisconnected, self.onMQTTPublish, self.onMQTTSubscribed)

        Domoticz.Log("Started Heartbeat")
        Domoticz.Heartbeat(10)
 
    def createDevices(self):
        Domoticz.Log("Filler")

    def getConfigItem(self, Key=None, Default={}):
        Value = Default
        try:
            Config = Domoticz.Configuration()
            if (Key != None):
                Value = Config[Key] # only return requested key if there was one
            else:
                Value = Config      # return the whole configuration if no key
        except KeyError:
            Value = Default
        except Exception as inst:
            Domoticz.Error("Domoticz.Configuration read failed: '"+str(inst)+"'")
        return Value
    
    def setConfigItem(self, Key=None, Value=None):
        Config = {}
        try:
            Config = Domoticz.Configuration()
            if (Key != None):
                Config[Key] = Value
            else:
                Config = Value  # set whole configuration if no key specified
            Domoticz.Configuration(Config)
        except Exception as inst:
            Domoticz.Error("Domoticz.Configuration operation failed: '"+str(inst)+"'")
        return Config

    def onDeviceRemoved(self, Unit):
        Domoticz.Log('Device Removed: {0}'.format(Unit))

    def onStop(self):
        Domoticz.Log("Stopping")
#        self.mqttClient.loop_stop()

    def onConnect(self, Connection, Status, Description):
       if self.mqttClient is not None:
        self.mqttClient.onConnect(Connection, Status, Description)

    def onDisconnect(self, Connection):
       if self.mqttClient is not None:
        self.mqttClient.onDisconnect(Connection)

    def onMessage(self, Connection, Data):
       if self.mqttClient is not None:
        self.mqttClient.onMessage(Connection, Data)

    def onHeartbeat(self):
        if self.mqttClient is not None:
            try:
                if (self.mqttClient._connection is None) or (not self.mqttClient.isConnected):
                    Domoticz.Log("Reconnecting")
                    self.mqttClient._open()
                else:
                    self.mqttClient.ping()
            except Exception as e:
                Domoticz.Error(str(e))


    def firstFreeUnit(self):
        for x in range(1,255):
            if not (x in Devices):
#                Domoticz.Log(str(x))
                return x
        return -1

    def sendCommand(self, command):
        url = 'http://{0}/api/v1/otgw/command/{1}'.format(self.otgwserveraddress, command)
        ret = post(url)
        Domoticz.Debug(ret.text)

    def onMQTTConnected(self):
       if self.mqttClient is not None:
        self.mqttClient.subscribe([self.base_topic + '/#'])
        self.mqttClient.subscribe([self.otgw_topic + '/#'])

    def onMQTTDisconnected(self):
        Domoticz.Debug("onMQTTDisconnected")

    def onMQTTSubscribed(self):
        Domoticz.Debug("onMQTTSubscribed")

    def onMQTTPublish(self, topic, message): # process incoming MQTT statuses
        if '/config' in topic:
            data = message
            deviceName = data['name'] #.split('/')[1]

            for tempDev in self.getConfigItem().keys():
                if data['state_topic'] == self.getConfigItem(tempDev):
                    Domoticz.Log('Device already exists: {0}' .format(deviceName))

            isBinary = "binary_sensor" in topic
            hasDeviceClass = "device_class" in data
            hasUnitOfMeasurement = "unit_of_measurement"
            if isBinary:
                deviceType = 'Switch'
            elif hasDeviceClass:
                deviceType = data['device_class']
            else:
                unitMes = data['unit_of_measurement']
                if unitMes == '%':
                    deviceType = 'Percentage'
                elif unitMes == 'l/min':
                    deviceType = 'Waterflow'
                elif unitMes == 'bar':
                    deviceType = 'Pressure'
                else:
                    deviceType = 'Counter'

            if hasDeviceClass:
                if data['device_class'] == 'temperature' and 'set' in data['state_topic'].lower():
                    deviceType = 'Thermostat'
                elif data['device_class'] == 'temperature':
                    deviceType = 'Temperature'

            freeUnit = self.firstFreeUnit()

            if freeUnit == -1:
                Domotic.Log("Too Many Devices")
                return

            Domoticz.Log("Creating Device " + deviceName)
            typeNames = ['Percentage', 'Waterflow', 'Pressure', 'Temperature', 'Switch']
            if deviceType in typeNames:
                Domoticz.Device(Name=deviceName, Used=0, Unit=freeUnit, TypeName=deviceType, Description=data['state_topic']).Create()
                self.setConfigItem(str(freeUnit), data['state_topic'])
            elif deviceType == 'Counter':
                Options={'Custom':'1;#'}
                Domoticz.Device(Name=deviceName, Unit=freeUnit, Type=243, Subtype=31, Used=0, Description=data['state_topic'], Options=Options).Create()
                self.setConfigItem(str(freeUnit), data['state_topic'])
            elif deviceType == 'Thermostat':
                Domoticz.Device(Name=deviceName, Unit=freeUnit, Type=242, Subtype=1, Used=0, Description=data['state_topic']).Create()
                self.setConfigItem(str(freeUnit), data['state_topic'])

            else:
                Domoticz.Log("Unknown Device")

        else:
            for tempDev2 in self.getConfigItem().keys():
                if topic == self.getConfigItem(tempDev2):
                    Domoticz.Log("Config found: " + self.getConfigItem(tempDev2))
                    if int(tempDev2) in Devices:
                        Devices[int(tempDev2)].Update(0, str(message))
                    break

    def onCommand(self, Unit, Command, Level, Hue):
        #Domoticz.Log("Command: Unit: {0}; Command {1}; Level {2}; Hue {3}".format(Unit,Command,Level,Hue))
        #Domoticz.Log('{0} : {1}'.format(Unit ,Devices[Unit].Description))
        devTopic = self.getConfigItem(str(Unit))
        if '/ ' in devTopic:
            devTopic = devTopic.split('/')[1] # remove OTGW/
        else:
            Domoticz.Log("Command aborted, device has no valid MQTT Topic")
            return #something wrong with the MQTT Topic
        #todo: add all setpoints
        if devTopic == 'TrSet':  # set room temprature
            self.mqttClient.publish(self.otgw_topic + '/command', 'TT={0}'.format(str(Level)))


global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)

def onConnect(Connection, Status, Description):
    global _plugin
    _plugin.onConnect(Connection, Status, Description)

def onDisconnect(Connection):
    global _plugin
    _plugin.onDisconnect(Connection)

def onMessage(Connection, Data):
    global _plugin
    _plugin.onMessage(Connection, Data)


def onDeviceRemoved():
    global _plugin
    _plugin.onDeviceRemoved()
