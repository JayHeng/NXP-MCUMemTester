#! /usr/bin/env python
# -*- coding: UTF-8 -*-
import sys
import os
import time
from PyQt5.Qt import *
from ui import uidef
from ui import uilang
from ui import uivar
from ui import ui_cfg_flexspi_conn
from ui import ui_cfg_flexspi_pintest
from ui import ui_cfg_perf_test
from ui import ui_cfg_stress_test
from run import runcore

kRetryPingTimes = 5
s_goAction = None

class memTesterMain(runcore.memTesterRun):

    def __init__(self, parent=None):
        super(memTesterMain, self).__init__(parent)
        self._register_callbacks()
        self.isDeviceConnected = False
        self._setupMcuTargets()

    def _register_callbacks(self):
        self.menuHelpAction_homePage.triggered.connect(self.callbackShowHomePage)
        self.menuHelpAction_aboutAuthor.triggered.connect(self.callbackShowAboutAuthor)
        self.menuHelpAction_revisionHistory.triggered.connect(self.callbackShowRevisionHistory)
        self.comboBox_mcuDevice.currentIndexChanged.connect(self.callbackSetMcuDevice)
        self.pushButton_flexspiConnectionConfiguration.clicked.connect(self.callbackFlexspiConnectionConfiguration)
        self.pushButton_connect.clicked.connect(self.callbackConnectToDevice)
        self.comboBox_memType.currentIndexChanged.connect(self.callbackSetMemType)
        self.pushButton_pinUnittest.clicked.connect(self.callbackFlexspiPinUnittest)
        self.pushButton_configSystem.clicked.connect(self.callbackConfigSystem)
        self.pushButton_memInfo.clicked.connect(self.callbackMemInfo)
        self.pushButton_rwTest.clicked.connect(self.callbackRwTest)
        self.pushButton_perfTest.clicked.connect(self.callbackPerfTest)
        self.pushButton_stressTest.clicked.connect(self.callbackStressTest)
        self.pushButton_Go.clicked.connect(self.callbackGo)
        self.pushButton_clearScreen.clicked.connect(self.clearContentOfScreens)

    def _setupMcuTargets( self ):
        self.setTargetSetupValue()
        self.initUi()
        self.initRun()
        self.updateCpuSpeedInfo()
        self.updateUartPadInfo()

    def callbackSetMcuDevice( self ):
        self._setupMcuTargets()

    def callbackFlexspiConnectionConfiguration( self ):
        self.showContentOnSecPacketWin(u"【Action】: Click <FlexSPI Connnect Configuration> button.")
        flexspiConnCfgFrame.setNecessaryInfo(self.tgt.flexspiConnDict, self.textEdit_flexspiConnection)
        flexspiConnCfgFrame.show()

    def _retryToPingBootloader( self ):
        pingStatus = False
        pingCnt = kRetryPingTimes
        while (not pingStatus) and pingCnt > 0:
            pingStatus = self.pingRom()
            if pingStatus:
                break
            pingCnt = pingCnt - 1
            time.sleep(2)
        return pingStatus

    def callbackConnectToDevice( self ):
        if not self.isDeviceConnected:
            self.showContentOnSecPacketWin(u"【Action】: Click <Connect> button to load boot firmware.")
            self.updatePortSetupValue()
            self.connectToDevice()
            if True:#self._retryToPingBootloader():
                if True:#self.jumpToFirmware():
                    self.showContentOnSecPacketWin(u"【  Info 】: boot firmware is loaded.")
                    self.openUartPort()
                    self.isDeviceConnected = True
                else:
                    pass
            else:
                if (self.tgt.mcuSeries == uidef.kMcuSeries_iMXRT10yy) or \
                   (self.tgt.mcuSeries == uidef.kMcuSeries_iMXRT11yy):
                    self.showInfoMessage('Connection Error', uilang.kMsgLanguageContentDict['connectError_doubleCheckBmod'][0])
                elif (self.tgt.mcuSeries == uidef.kMcuSeries_iMXRTxxx):
                    self.showInfoMessage('Connection Error', uilang.kMsgLanguageContentDict['connectError_doubleCheckSerialMasterBoot'][0])
                else:
                    pass
        else:
            self.showContentOnSecPacketWin(u"【Action】: Click <Reset> button to reboot system.")
            self.isDeviceConnected = False
            self.closeUartPort()

    def callbackSetMemType( self ):
        self.setMemType()

    def callbackFlexspiPinUnittest( self ):
        self.showContentOnSecPacketWin(u"【Action】: Click <Pin Unittest> button.")
        global s_goAction
        s_goAction = uidef.kGoAction_PinUnittest
        flexspiPinUnittestFrame.show()
        self.resetAllActionButtonColor()
        self.setActionButtonColor(s_goAction)

    def callbackConfigSystem( self ):
        self.showContentOnSecPacketWin(u"【Action】: Click <Config System> button.")
        global s_goAction
        s_goAction = uidef.kGoAction_ConfigSystem
        self.resetAllActionButtonColor()
        self.setActionButtonColor(s_goAction)

    def callbackMemInfo( self ):
        self.showContentOnSecPacketWin(u"【Action】: Click <Mem Info> button.")
        global s_goAction
        s_goAction = uidef.kGoAction_MemInfo
        self.resetAllActionButtonColor()
        self.setActionButtonColor(s_goAction)

    def callbackRwTest( self ):
        self.showContentOnSecPacketWin(u"【Action】: Click <R/W Test> button.")
        global s_goAction
        s_goAction = uidef.kGoAction_RwTest
        self.resetAllActionButtonColor()
        self.setActionButtonColor(s_goAction)

    def callbackPerfTest( self ):
        self.showContentOnSecPacketWin(u"【Action】: Click <Perf Test> button.")
        global s_goAction
        s_goAction = uidef.kGoAction_PerfTest
        perfTestFrame.show()
        self.resetAllActionButtonColor()
        self.setActionButtonColor(s_goAction)

    def callbackStressTest( self ):
        self.showContentOnSecPacketWin(u"【Action】: Click <Stress Test> button.")
        global s_goAction
        s_goAction = uidef.kGoAction_StressTest
        stressTestFrame.show()
        self.resetAllActionButtonColor()
        self.setActionButtonColor(s_goAction)

    def callbackGo( self ):
        global s_goAction
        if s_goAction == None:
            return
        if self.isGoActionWorking():
            self.showContentOnSecPacketWin(u"【Action】: Click <Stop> button.")
            self.sendTestStopPacket()
            self.resetAllActionButtonColor()
            s_goAction = None
            self.recoverGoActionButton()
        else:
            self.showContentOnSecPacketWin(u"【Action】: Click <Go> button.")
        if s_goAction == uidef.kGoAction_PinUnittest:
            self.sendPinTestPacket()
        elif s_goAction == uidef.kGoAction_ConfigSystem:
            if self.updateTargetSetupValue():
                self.sendConfigSystemPacket()
            else:
                return
        elif s_goAction == uidef.kGoAction_MemInfo:
            pass
        elif s_goAction == uidef.kGoAction_RwTest:
            self.sendRwTestPacket()
        elif s_goAction == uidef.kGoAction_PerfTest:
            pass
        elif s_goAction == uidef.kGoAction_StressTest:
            pass
        else:
            return
        self.updateGoActionButton()

    def _deinitToolToExit( self ):
        uivar.setAdvancedSettings(uidef.kAdvancedSettings_Tool, self.toolCommDict)
        uivar.deinitVar()

    def closeEvent(self, event):
        self._deinitToolToExit()
        event.accept()

    def callbackShowHomePage(self):
        self.showAboutMessage(uilang.kMsgLanguageContentDict['homePage_title'][0], uilang.kMsgLanguageContentDict['homePage_info'][0] )

    def callbackShowAboutAuthor(self):
        msgText = ((uilang.kMsgLanguageContentDict['aboutAuthor_author'][0]) +
                   (uilang.kMsgLanguageContentDict['aboutAuthor_email1'][0]) +
                   (uilang.kMsgLanguageContentDict['aboutAuthor_email2'][0]) +
                   (uilang.kMsgLanguageContentDict['aboutAuthor_blog'][0]))
        self.showAboutMessage(uilang.kMsgLanguageContentDict['aboutAuthor_title'][0], msgText )

    def callbackShowRevisionHistory(self):
        self.showAboutMessage(uilang.kMsgLanguageContentDict['revisionHistory_title'][0], uilang.kMsgLanguageContentDict['revisionHistory_v0_1_0'][0] )

if __name__ == '__main__':
    app = QApplication(sys.argv)
    mainWin = memTesterMain(None)
    mainWin.setWindowTitle(u"MCU Mem Test Utility v0.1")
    mainWin.show()
    flexspiConnCfgFrame = ui_cfg_flexspi_conn.memTesterUiCfgFlexspiConn(None)
    flexspiConnCfgFrame.setWindowTitle(u"FlexSPI Connection Configuration")
    flexspiPinUnittestFrame = ui_cfg_flexspi_pintest.memTesterUiCfgFlexspiPin(None)
    flexspiPinUnittestFrame.setWindowTitle(u"FlexSPI Pin Unit Test")
    perfTestFrame = ui_cfg_perf_test.memTesterUiPerfTest(None)
    perfTestFrame.setWindowTitle(u"Perf Test")
    stressTestFrame = ui_cfg_stress_test.memTesterUiStressTest(None)
    stressTestFrame.setWindowTitle(u"Stress Test")

    sys.exit(app.exec_())

