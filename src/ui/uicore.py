#! /usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2022 NXP
# All rights reserved.
# 
# SPDX-License-Identifier: BSD-3-Clause

import sys
import os
import serial.tools.list_ports
from PyQt5.Qt import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

import matplotlib
matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import matplotlib.animation as animation

from . import uidef
from . import uilang
from . import uivar
from . import uilut
from . import uipacket
from . import ui_def_flexspi_conn_rt500
from . import ui_def_flexspi_conn_rt600
from . import ui_def_xspi_conn_rt700
from . import ui_def_flexspi_conn_rt1060
from . import ui_def_flexspi_conn_rt1170
from . import ui_def_flexspi_conn_rt1180
sys.path.append(os.path.abspath(".."))
from win import memTesterWin
from boot import model
from utils import misc

s_serialPort = serial.Serial()
s_recvInterval = 1
s_recvPinWave = [0] * 100
s_isRecvAsciiMode = True
s_recvUartMagic = ""

def createModel(modelDescFile):
    # Check for model file existence.
    if not os.path.isfile(modelDescFile):
        raise RuntimeError("Missing model file at path %s" % modelDescFile)

    # Build locals dict by copying our locals and adjusting file path and name.
    modelDesc = locals().copy()
    modelDesc['__file__'] = modelDescFile

    # Execute the model desc script.
    misc.execfile(modelDescFile, globals(), modelDesc)

    # Create the model object.
    mdl = model.Model(**modelDesc)

    return mdl

class uartRecvWorker(QThread):
    sinOut = pyqtSignal()

    def __init__(self, parent=None):
        super(uartRecvWorker, self).__init__(parent)
        self.working = True

    def __del__(self):
        self.working = False

    def run(self):
        while self.working == True:
            self.sinOut.emit()
            self.sleep(s_recvInterval)

class pinWaveformFigure(FigureCanvas):

    def __init__(self,width=5, height=4, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        super(pinWaveformFigure,self).__init__(self.fig)
        self.axes = self.fig.add_subplot(111)
        self.axes.set_xlabel('Time(ms)')
        self.axes.set_ylabel('Volt(3.3V)')
        self.axes.set_ylim(0,1.1)
        self.plotwave()
        self.ani = animation.FuncAnimation(self.fig, self.animate, interval=1000, blit=True, save_count=50)

    def plotwave(self):
        self.line, = self.axes.plot(s_recvPinWave)

    def animate(self, i):
        #global s_recvPinWave
        #for i in range(len(s_recvPinWave)):
        #    s_recvPinWave[i] = (int(i/10) % 2)
        self.line.set_ydata(s_recvPinWave)
        return self.line,

class memTesterUi(QMainWindow, memTesterWin.Ui_memTesterWin):

    def __init__(self, parent=None):
        super(memTesterUi, self).__init__(parent)
        self.setupUi(self)
        self.uartRecvThread = uartRecvWorker()
        self.uartRecvThread.sinOut.connect(self.receiveUartData)

        self.exeBinRoot = os.getcwd()
        self.exeTopRoot = os.path.dirname(self.exeBinRoot)
        exeMainFile = os.path.join(self.exeTopRoot, 'src', 'main.py')
        if not os.path.isfile(exeMainFile):
            self.exeTopRoot = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self.memModelRoot = os.path.join(os.path.dirname(self.exeBinRoot), 'src', 'targets', 'mem_model')
        uivar.setRuntimeSettings(None, self.exeTopRoot)
        uivar.initVar(os.path.join(self.exeTopRoot, 'bin', 'mtu_settings.json'))
        toolCommDict = uivar.getAdvancedSettings(uidef.kAdvancedSettings_Tool)
        self.toolCommDict = toolCommDict.copy()
        self.mixspiConnCfgDict = None

        self.mcuDevice = None
        self._initTargetSetupValue()
        self.setTargetSetupValue()
        self.initFuncUi()
        self._initFlexspiConn()
        self.memModel = None
        self.memVendor = None
        self.memType = None
        self.memChip = None
        self._initMemVendor()
        self.memLut = []
        self.memPropertyDict = None

        self.pinWaveFig = pinWaveformFigure(width=2, height=4, dpi=50)
        self.pinWaveFig.plotwave()
        self.pinWaveGridlayout = QGridLayout(self.groupBox_pinWaveform)
        self.pinWaveGridlayout.addWidget(self.pinWaveFig,0,0)

    def initToolMenu( self ):
        self.loadFwActionGroup = QActionGroup(self)
        self.loadFwActionGroup.setExclusive(True)
        self.loadFwActionGroup.addAction(self.menuLoadFwAction_No)
        self.loadFwActionGroup.addAction(self.menuLoadFwAction_Yes)
        self.menuLoadFwAction_Yes.setChecked(self.toolCommDict['loadFwEn'])
        self.menuLoadFwAction_No.setChecked(not self.toolCommDict['loadFwEn'])
        self.setLoadFwOpt()
        self.showCmdPacketGroup = QActionGroup(self)
        self.showCmdPacketGroup.setExclusive(True)
        self.showCmdPacketGroup.addAction(self.menuShowCmdPacket_No)
        self.showCmdPacketGroup.addAction(self.menuShowCmdPacket_Yes)
        self.menuShowCmdPacket_Yes.setChecked(self.toolCommDict['cmdPacketShowEn'])
        self.menuShowCmdPacket_No.setChecked(not self.toolCommDict['cmdPacketShowEn'])
        self.setShowCmdPacketOpt()

    def setLoadFwOpt( self ):
        self.isLoadFirmwareEnabled = self.menuLoadFwAction_Yes.isChecked()
        self.toolCommDict['loadFwEn'] = self.isLoadFirmwareEnabled

    def setShowCmdPacketOpt( self ):
        self.isShowCmdPacketEnabled = self.menuShowCmdPacket_Yes.isChecked()
        self.toolCommDict['cmdPacketShowEn'] = self.isShowCmdPacketEnabled

    def initFuncUi( self ):
        self.uartComPort = None
        self.uartBaudrate = None
        self.setPortSetupValue()

    def showAboutMessage( self, myTitle, myContent):
        QMessageBox.about(self, myTitle, myContent )

    def showInfoMessage( self, myTitle, myContent):
        QMessageBox.information(self, myTitle, myContent )

    def updateCpuSpeedInfo( self ):
        self.lineEdit_cpuSpeed.setText(str(self.tgt.maxCpuFreqInMHz))

    def adjustPortSetupValue( self ):
        # Auto detect available ports
        comports = list(serial.tools.list_ports.comports())
        ports = [None] * len(comports)
        for i in range(len(comports)):
            comport = list(comports[i])
            ports[i] = comport[0]
        lastPort = self.comboBox_comPort.currentText()
        lastBaud = self.comboBox_baudrate.currentText()
        self.comboBox_comPort.clear()
        self.comboBox_comPort.addItems(ports)
        if lastPort in ports:
            self.comboBox_comPort.setCurrentIndex(self.comboBox_comPort.findText(lastPort))
        else:
            self.comboBox_comPort.setCurrentIndex(0)
        baudItems = ['115200']
        self.comboBox_baudrate.clear()
        self.comboBox_baudrate.addItems(baudItems)
        if lastBaud in baudItems:
            self.comboBox_baudrate.setCurrentIndex(self.comboBox_baudrate.findText(lastBaud))
        else:
            self.comboBox_baudrate.setCurrentIndex(0)

    def _initTargetSetupValue( self ):
        self.comboBox_mcuDevice.clear()
        self.comboBox_mcuDevice.addItems(uidef.kMcuDevice_v1_0)
        self.comboBox_mcuDevice.setCurrentIndex(self.toolCommDict['mcuDevice'])
        self.lineEdit_cpuSpeed.setText(str(self.toolCommDict['cpuSpeedMHz']))
        if self.toolCommDict['enableL1Cache']:
            self.checkBox_enableL1Cache.setChecked(True)
        else:
            self.checkBox_enableL1Cache.setChecked(False)
        if self.toolCommDict['enablePrefetch']:
            self.checkBox_enablePrefetch.setChecked(True)
        else:
            self.checkBox_enablePrefetch.setChecked(False)

    def setTargetSetupValue( self ):
        self.mcuDevice = self.comboBox_mcuDevice.currentText()
        self.toolCommDict['mcuDevice'] = self.comboBox_mcuDevice.currentIndex()

    def _initFlexspiConn( self ):
        mixspiConnCfgDict = uivar.getAdvancedSettings(uidef.kAdvancedSettings_Conn)
        self.mixspiConnCfgDict = mixspiConnCfgDict.copy()
        instance = self.mixspiConnCfgDict['instance'] - 1
        self.textEdit_mixspiConnection.clear()
        mixspiConnSelDict = None
        if self.mcuDevice == uidef.kMcuDevice_iMXRT500:
            mixspiConnSelDict = ui_def_flexspi_conn_rt500.kFlexspiConnSelDict.copy()
        elif self.mcuDevice == uidef.kMcuDevice_iMXRT600:
            mixspiConnSelDict = ui_def_flexspi_conn_rt600.kFlexspiConnSelDict.copy()
        elif self.mcuDevice == uidef.kMcuDevice_iMXRT700:
            mixspiConnSelDict = ui_def_xspi_conn_rt700.kXspiConnSelDict.copy()
        elif self.mcuDevice == uidef.kMcuDevice_iMXRT106x:
            mixspiConnSelDict = ui_def_flexspi_conn_rt1060.kFlexspiConnSelDict.copy()
        elif self.mcuDevice == uidef.kMcuDevice_iMXRT117x:
            mixspiConnSelDict = ui_def_flexspi_conn_rt1170.kFlexspiConnSelDict.copy()
        elif self.mcuDevice == uidef.kMcuDevice_iMXRT118x:
            mixspiConnSelDict = ui_def_flexspi_conn_rt1180.kFlexspiConnSelDict.copy()
        else:
            pass

        for key in mixspiConnSelDict['dataL4b'][instance].keys():
            if mixspiConnSelDict['dataL4b'][instance][key] == self.mixspiConnCfgDict['dataL4b']:
                self.textEdit_mixspiConnection.append(key)
                break
        for key in mixspiConnSelDict['dataH4b'][instance].keys():
            if mixspiConnSelDict['dataH4b'][instance][key] == self.mixspiConnCfgDict['dataH4b']:
                if key != 'None':
                    self.textEdit_mixspiConnection.append(key)
                break
        for key in mixspiConnSelDict['dataT8b'][instance].keys():
            if mixspiConnSelDict['dataT8b'][instance][key] == self.mixspiConnCfgDict['dataT8b']:
                if key != 'None':
                    self.textEdit_mixspiConnection.append(key)
                break
        for key in mixspiConnSelDict['ssb'][instance].keys():
            if mixspiConnSelDict['ssb'][instance][key] == self.mixspiConnCfgDict['ssb']:
                self.textEdit_mixspiConnection.append(key)
                break
        for key in mixspiConnSelDict['sclk'][instance].keys():
            if mixspiConnSelDict['sclk'][instance][key] == self.mixspiConnCfgDict['sclk']:
                self.textEdit_mixspiConnection.append(key)
                break
        for key in mixspiConnSelDict['sclkn'][instance].keys():
            if mixspiConnSelDict['sclkn'][instance][key] == self.mixspiConnCfgDict['sclkn']:
                if key != 'None':
                    self.textEdit_mixspiConnection.append(key)
                break
        for key in mixspiConnSelDict['dqs0'][instance].keys():
            if mixspiConnSelDict['dqs0'][instance][key] == self.mixspiConnCfgDict['dqs0']:
                if key != 'None':
                    self.textEdit_mixspiConnection.append(key)
                break
        for key in mixspiConnSelDict['dqs1'][instance].keys():
            if mixspiConnSelDict['dqs1'][instance][key] == self.mixspiConnCfgDict['dqs1']:
                if key != 'None':
                    self.textEdit_mixspiConnection.append(key)
                break
        for key in mixspiConnSelDict['rstb'][instance].keys():
            if mixspiConnSelDict['rstb'][instance][key] == self.mixspiConnCfgDict['rstb']:
                if key != 'None':
                    self.textEdit_mixspiConnection.append(key)
                break

    def updateTargetSetupValue( self ):
        try:
            cpuSpeed = int(self.lineEdit_cpuSpeed.text())
            if cpuSpeed > self.tgt.maxCpuFreqInMHz:
                self.showInfoMessage('Range Error', 'cpu speed should not be more than max freq ' + str(self.tgt.maxCpuFreqInMHz) + ' MHz!')
                return False
            self.toolCommDict['cpuSpeedMHz'] = cpuSpeed
        except:
            self.showInfoMessage('Input Error', 'cpu speed should be an integer!')
            return False
        if self.checkBox_enableL1Cache.isChecked():
            self.toolCommDict['enableL1Cache'] = 1
        else:
            self.toolCommDict['enableL1Cache'] = 0
        if self.checkBox_enablePrefetch.isChecked():
            self.toolCommDict['enablePrefetch'] = 1
        else:
            self.toolCommDict['enablePrefetch'] = 0
        uivar.setAdvancedSettings(uidef.kAdvancedSettings_Tool, self.toolCommDict)
        return True

    def updateUartPadInfo( self ):
        self.lineEdit_uartPad.setText(self.tgt.uartPeripheralPinStr)

    def updatePortSetupValue( self ):
        self.uartComPort = self.comboBox_comPort.currentText()
        self.uartBaudrate = self.comboBox_baudrate.currentText()

    def setPortSetupValue( self ):
        self.adjustPortSetupValue()
        self.updatePortSetupValue()

    def openUartPort ( self ):
        s_serialPort.port = self.uartComPort
        s_serialPort.baudrate = int(self.uartBaudrate)
        s_serialPort.bytesizes = serial.EIGHTBITS
        s_serialPort.stopbits = serial.STOPBITS_ONE
        s_serialPort.parity = serial.PARITY_NONE
        try:
            s_serialPort.open()
        except:
            QMessageBox.information(self, 'Port Error', 'Com Port cannot opened!')
            return
        s_serialPort.set_buffer_size(rx_size=1024 * 16)
        s_serialPort.reset_input_buffer()
        s_serialPort.reset_output_buffer()
        self.uartRecvThread.start()
        self.pushButton_connect.setText('Reset')
        self.pushButton_connect.setStyleSheet("background-color: green")

    def closeUartPort ( self ):
        if s_serialPort.isOpen():
            s_serialPort.close()
            self.uartRecvThread.quit()
            self.pushButton_connect.setText('Connect')
            self.pushButton_connect.setStyleSheet("background-color: grey")

    def _findUartPrintSwitchMagic( self, uartData, magic ):
        global s_recvUartMagic
        status = None
        string = ""
        try:
            string += uartData.decode('utf-8')
            if len(string) > len(magic):
                status = False
            elif string in magic:
                status = True
                s_recvUartMagic += string
            else:
                status = False
        except:
            pass
        return status, string

    def receiveUartData( self ):
        global s_isRecvAsciiMode
        global s_recvUartMagic
        if s_serialPort.isOpen():
            num = s_serialPort.inWaiting()
            if num != 0:
                #self.showContentOnMainDisplayWin('Get {:} bytes from UART\r\n'.format(num))
                data = s_serialPort.read(num)
                if not s_isRecvAsciiMode:
                    status, string = self._findUartPrintSwitchMagic(data, "Switch_To_ASCII_Mode")
                    if status:
                        if s_recvUartMagic == "Switch_To_ASCII_Mode":
                            s_isRecvAsciiMode = True
                            s_recvUartMagic = ""
                            #self.showContentOnMainDisplayWin("  __it is ascii mode")
                    else:
                        global s_recvPinWave
                        # We just use first 20 conv result each time
                        if num >= 20:
                            # To show square, every conv reslur will repeat 5 times in s_recvPinWave
                            for i in range(len(s_recvPinWave)):
                                s_recvPinWave[i] = data[int(i/5)]
                        #self.showContentOnMainDisplayWin("  __it is in hex mode output")
                    return
                else:
                    status, string = self._findUartPrintSwitchMagic(data, "Switch_To_HEX8B_Mode")
                    if status:
                        if s_recvUartMagic == "Switch_To_HEX8B_Mode":
                            s_isRecvAsciiMode = False
                            s_recvUartMagic = ""
                            #self.showContentOnMainDisplayWin("  __it is hex mode")
                    else:
                         self.showContentOnMainDisplayWin(string)

    def sendUartData( self , byteList ):
        if s_serialPort.isOpen():
            #num = s_serialPort.out_waiting()
            #while num != 0:
            #    num = s_serialPort.out_waiting()
            s_serialPort.write(byteList)
            if self.isShowCmdPacketEnabled:
                packetStr = ''
                for i in range(len(byteList)):
                    packetStr = packetStr + hex(byteList[i])
                    if i != len(byteList) - 1:
                        packetStr = packetStr + ', '
                self.showContentOnSecPacketWin(u"Cmd Packet ->: " + packetStr)

    def sendPinTestPacket( self ):
        mypacket = uipacket.pinTestPacket()
        mypacket.set_members()
        self.sendUartData(mypacket.out_bytes())

    def sendConfigSystemPacket( self ):
        self.getMemUserSettings()
        mypacket = uipacket.configSystemPacket(self.memLut, self.memModel.memPropertyDict)
        mypacket.set_members(self.toolCommDict)
        self.sendUartData(mypacket.out_bytes())

    def sendMemRegsPacket( self ):
        mypacket = uipacket.memRegsPacket()
        mypacket.set_members()
        self.sendUartData(mypacket.out_bytes())

    def sendRwTestPacket( self ):
        mypacket = uipacket.rwTestPacket()
        mypacket.set_members()
        self.sendUartData(mypacket.out_bytes())

    def sendPerfTestPacket( self ):
        mypacket = uipacket.perfTestPacket()
        mypacket.set_members()
        self.sendUartData(mypacket.out_bytes())

    def sendStressTestPacket( self ):
        mypacket = uipacket.stressTestPacket()
        mypacket.set_members()
        self.sendUartData(mypacket.out_bytes())

    def sendTestStopPacket( self ):
        mypacket = uipacket.testStopPacket()
        mypacket.set_members()
        self.sendUartData(mypacket.out_bytes())

    def _initMemVendor( self ):
        self.comboBox_memVendor.clear()
        self.comboBox_memVendor.addItems(uidef.kMemVendorList)
        self.comboBox_memVendor.setCurrentIndex(0)
        self.setMemVendor()

    def _findMemTypesFromVendor( self ):
        vendorBaseDir = os.path.join(self.memModelRoot, self.memVendor)
        return os.listdir(vendorBaseDir)

    def setMemVendor( self ):
        try:
            self.memVendor = self.comboBox_memVendor.currentText()
            #print(self.memVendor)
            self.comboBox_memType.clear()
            #self.comboBox_memType.addItems(uidef.kMemDeviceDict[self.memVendor].keys())
            self.comboBox_memType.addItems(self._findMemTypesFromVendor())
            self.comboBox_memType.setCurrentIndex(0)
            self.setMemType()
        except:
            pass

    def _findMemChipsFromType( self ):
        typeBaseDir = os.path.join(self.memModelRoot, self.memVendor, self.memType)
        files = os.listdir(typeBaseDir)
        pyfiles = [file for file in files if file.endswith('.py')]
        filenames = []
        for pyfile in pyfiles:
            filename, filetype = os.path.splitext(pyfile)
            filenames.append(filename)
        return filenames

    def setMemType( self ):
        try:
            self.memType = self.comboBox_memType.currentText()
            #print(self.memType)
            self.comboBox_memChip.clear()
            #self.comboBox_memChip.addItems(uidef.kMemDeviceDict[self.memVendor][self.memType])
            self.comboBox_memChip.addItems(self._findMemChipsFromType())
            self.comboBox_memChip.setCurrentIndex(0)
        except:
            pass

    def _getMemChipInfo( self ):
        self.memChip = self.comboBox_memChip.currentText()
        modelDescFile = os.path.join(self.memModelRoot, self.memVendor, self.memType, self.memChip + '.py')
        self.memModel = createModel(modelDescFile)
        try:
            if self.memType == uidef.kMemType_QuadSPI or \
               self.memType == uidef.kMemType_OctalSPI:
                self.memLut = uilut.generateCompleteNorLut(self.memModel.mixspiLutDict)
            elif self.memType == uidef.kMemType_PSRAM or \
                 self.memType == uidef.kMemType_HyperRAM:
                self.memLut = uilut.generateCompleteRamLut(self.memModel.mixspiLutDict)
            else:
                self.memLut = None
        except:
            self.memLut = None

    def _convertMemTypeValue(self, typeStr):
        for i in range(len(uidef.kMemTypeList)):
            if uidef.kMemTypeList[i] == typeStr:
                return i
        return 0

    def getMemUserSettings( self ):
        self._getMemChipInfo()
        memType = self.comboBox_memType.currentText()
        self.toolCommDict['memType'] = self._convertMemTypeValue(memType)
        memSpeed = self.comboBox_memSpeed.currentText()
        spdIdx = memSpeed.find('MHz')
        self.toolCommDict['memSpeed'] = int(memSpeed[0:spdIdx])

    def showContentOnMainDisplayWin( self, contentStr ):
        if self.goAction == uidef.kGoAction_PinTest or \
           self.goAction == uidef.kGoAction_ConfigSystem:
            self.textEdit_displayWin.append(contentStr)
        elif self.goAction == uidef.kGoAction_MemRegs:
            self.textEdit_displayWinReg.append(contentStr)
        elif self.goAction == uidef.kGoAction_RwTest or \
             self.goAction == uidef.kGoAction_PerfTest or \
             self.goAction == uidef.kGoAction_StressTest:
            self.textEdit_displayWinTest.append(contentStr)
        else:
            self.textEdit_displayWin.append(contentStr)

    def showContentOnSecPacketWin( self, contentStr ):
        self.textEdit_packetWin.append(contentStr)

    def clearContentOfScreens( self ):
        if self.goAction == uidef.kGoAction_PinTest or \
           self.goAction == uidef.kGoAction_ConfigSystem:
            self.textEdit_displayWin.clear()
        elif self.goAction == uidef.kGoAction_MemRegs:
            self.textEdit_displayWinReg.clear()
        elif self.goAction == uidef.kGoAction_RwTest or \
             self.goAction == uidef.kGoAction_PerfTest or \
             self.goAction == uidef.kGoAction_StressTest:
            self.textEdit_displayWinTest.clear()
        else:
            self.textEdit_displayWin.clear()
        self.textEdit_packetWin.clear()

    def resetAllActionButtonColor( self ):
        self.pushButton_pinTest.setStyleSheet("background-color: " + uidef.kButtonColor_Disable)
        self.pushButton_configSystem.setStyleSheet("background-color: " + uidef.kButtonColor_Disable)
        self.pushButton_memRegs.setStyleSheet("background-color: " + uidef.kButtonColor_Disable)
        self.pushButton_rwTest.setStyleSheet("background-color: " + uidef.kButtonColor_Disable)
        self.pushButton_perfTest.setStyleSheet("background-color: " + uidef.kButtonColor_Disable)
        self.pushButton_stressTest.setStyleSheet("background-color: " + uidef.kButtonColor_Disable)
        self.textEdit_displayWin.setStyleSheet("background-color: " + uidef.kButtonColor_Disable)
        self.textEdit_displayWinReg.setStyleSheet("background-color: " + uidef.kButtonColor_Disable)
        self.textEdit_displayWinTest.setStyleSheet("background-color: " + uidef.kButtonColor_Disable)

    def setActionButtonColor( self, goAction ):
        if goAction == uidef.kGoAction_PinTest:
            self.pushButton_pinTest.setStyleSheet("background-color: " + uidef.kButtonColor_Enable)
            self.textEdit_displayWin.setStyleSheet("background-color: " + uidef.kButtonColor_Enable)
        elif goAction == uidef.kGoAction_ConfigSystem:
            self.pushButton_configSystem.setStyleSheet("background-color: " + uidef.kButtonColor_Enable)
            self.textEdit_displayWin.setStyleSheet("background-color: " + uidef.kButtonColor_Enable)
        elif goAction == uidef.kGoAction_MemRegs:
            self.pushButton_memRegs.setStyleSheet("background-color: " + uidef.kButtonColor_Enable)
            self.textEdit_displayWinReg.setStyleSheet("background-color: " + uidef.kButtonColor_Enable)
        elif goAction == uidef.kGoAction_RwTest:
            self.pushButton_rwTest.setStyleSheet("background-color: " + uidef.kButtonColor_Enable)
            self.textEdit_displayWinTest.setStyleSheet("background-color: " + uidef.kButtonColor_Enable)
        elif goAction == uidef.kGoAction_PerfTest:
            self.pushButton_perfTest.setStyleSheet("background-color: " + uidef.kButtonColor_Enable)
            self.textEdit_displayWinTest.setStyleSheet("background-color: " + uidef.kButtonColor_Enable)
        elif goAction == uidef.kGoAction_StressTest:
            self.pushButton_stressTest.setStyleSheet("background-color: " + uidef.kButtonColor_Enable)
            self.textEdit_displayWinTest.setStyleSheet("background-color: " + uidef.kButtonColor_Enable)
        else:
            pass

    def isGoActionWorking( self ):
        return (self.pushButton_Go.text() == "Stop")

    def updateGoActionButton( self ):
        self.pushButton_Go.setText("Stop")

    def recoverGoActionButton( self ):
        self.pushButton_Go.setText("Go")
