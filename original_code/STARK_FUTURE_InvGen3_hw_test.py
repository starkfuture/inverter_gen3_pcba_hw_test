## Needed Imports
import time
import threading
from PCANBasic import *
from datetime import datetime, timedelta
import STARK_FUTURE_hw_test_protocol as sf_protocol


class InvGen3HardwareTestOverCAN():

    # Defines
    #region
    APP_HW_TEST_VERSION_MAJOR = 0
    APP_HW_TEST_VERSION_MINOR = 9

    APP_HW_TEST_DUMMY_COMMS = False

    APP_USER_CMDS_SHORTCUT_INDEX = 0
    APP_USER_CMDS_COMMENT_INDEX = 1

    APP_TRACE_MODE_DISABLED = 0
    APP_TRACE_MODE_ENABLED = 1
    APP_TRACE_MODE_ONLY_DIFFERENCE = 2

    APP_TRACE_CAUSE_NO_TRACE = 0
    APP_TRACE_CAUSE_USER_INFO = 1
    APP_TRACE_CAUSE_OBJECT_ADDED = 2
    APP_TRACE_CAUSE_OBJECT_CHANGE = 3
    APP_TRACE_CAUSE_OBJECT_NO_CHANGE = 4

    APP_HW_TEST_SEQ_QUANTUM_TIME_IN_MS = 20
    APP_HW_TEST_MACRO_QUANTUM_TIME_IN_MS = 10

    APP_HW_TEST_MACRO_INVALID_STEP = 1000

    # Sets the PCANHandle (Hardware Channel)
    PcanHandle = PCAN_USBBUS1

    # Sets the desired connection mode (CAN = false / CAN-FD = true)
    IsFD = False

    # Sets the bitrate for normal CAN devices
    Bitrate = PCAN_BAUD_250K

    # Sets the bitrate for CAN FD devices.
    # Example - Bitrate Nom: 1Mbit/s Data: 2Mbit/s:
    #   "f_clock_mhz=20, nom_brp=5, nom_tseg1=2, nom_tseg2=1, nom_sjw=1, data_brp=2, data_tseg1=3, data_tseg2=1, data_sjw=1"
    BitrateFD = b'f_clock_mhz=20, nom_brp=5, nom_tseg1=2, nom_tseg2=1, nom_sjw=1, data_brp=2, data_tseg1=3, data_tseg2=1, data_sjw=1'

    #endregion

    # Members
    #region

    # Shows if DLL was found
    m_DLLFound = False

    #endregion

    def __init__(self):
        """
        Create an object starts the program
        """
        self.ShowSplashScreen() ## Shows initial information about this application
        # self.ShowCurrentConfiguration() ## Shows the current parameters configuration

        ## Initialization of CAN interface
        self.m_objPCANBasic = None
        self.m_DLLFound = False
        if not self.APP_HW_TEST_DUMMY_COMMS:
            self.m_CANStarted = self.startCANCommunicationsHardwareInterface()
        else:
            self.m_CANStarted = True

        ## Initialization of protocol information
        self.m_prot_manager = sf_protocol.sfHwTestProtocol()
        self.m_protocol_canid = self.m_prot_manager.sfHwTestProtocolGetCANid()
        self.m_protocol_requests = self.m_prot_manager.sfHwTestProtocolGetRequestsDictionary()
        self.m_protocol_tests_dict = self.m_prot_manager.sfHwTestProtocolGetTestsDictionary()
        self.m_protocol_tests_seq_list = self.m_prot_manager.sfHwTestProtocolGetTestsSequencesList()
        self.m_protocol_tests_seq_steps_list = self.m_prot_manager.sfHwTestProtocolGetMinimumASampleTestsList()

        ## Initialization of internal dictionaries
        self.m_user_cmds_dict = self.getUserCommandsDictionary()
        self.m_user_pwms_dict = self.getPwmsDictionary()
        self.m_user_dig_outs_dict = self.getDigOuputsDictionary()
        self.m_user_macros_dict = self.getUserMacrosDictionary()
        self.m_reported_objects = dict() # received values

        ## Initialization of configuration
        self.m_trace_enabled = self.APP_TRACE_MODE_DISABLED

        ## Initialization of state variables
        self.m_ConsoleRun = False
        self.m_objReadThread = None
        self.m_ListeningRun = False
        self.m_sequenceThread = None
        self.m_sequenceRun = False
        self.m_sequenceAsyncTrigger = False
        self.m_sequenceInProgress = False
        self.m_sequenceState = 0
        self.m_sequenceItem = 0
        self.m_sequenceItemTimeout = 0
        self.m_sequencePeriodicRun = False
        self.m_sequencePeriodicIntervalInMinutes = 0
        self.m_sequencePeriodicIntervalInSeconds = 0
        self.m_sequencePeriodicNextTimestamp = datetime.now()
        self.m_sequenceSyncTrigger = False
        self.m_macroThread = None
        self.m_macroRun = False
        self.m_macroAsyncTrigger = False
        self.m_macroInProgress = False
        self.m_macroType = None
        self.m_macroState = 0
        self.m_macroCommandType = None
        self.m_macroInstance = 0
        self.m_macroStepTimeout = 0
        self.m_macroSweep = {
            "current": 0.0,
            "start": 0.0,
            "stop": 0.0,
            "step_amplitude": 0.0,
            "step_time_in_ms": 0.0,
        }
        self.m_macroTrapezoidal = {
            "current": 0.0,
            "start": 0.0,
            "seattle": 0.0,
            "stop": 0.0,
            "rise_step_amplitude": 0.0,
            "rise_step_time_in_ms": 0.0,
            "seattle_time_in_ms": 0.0,
            "fall_step_amplitude": 0.0,
            "fall_step_time_in_ms": 0.0,
        }
        self.m_logging_traces = False
        self.m_log_file_handler = None
        self.m_log_time_mask = ""

        if self.m_CANStarted:
            print("Successfully initialized.")

    def __del__(self):
        # Finishes log process (if it is active)
        self.EnableDisableLogToFile(False)

        # Disables CAN interface
        if self.m_DLLFound and self.m_CANStarted:
            self.m_objPCANBasic.Uninitialize(PCAN_NONEBUS)

    # Private functions
    def _ShowRequestsTypes(self):
        """
        Shows/prints the list of allowed tests (and information about them)
        """
        test_index = 1
        for test_key in self.m_protocol_requests.keys():
            print(" " + str(test_index) + ". " +
                  self.m_protocol_requests[test_key][self.m_prot_manager.SF_HW_TEST_PROTOCOL_MSG_COMMENT_INDEX])
            test_index = test_index + 1

        return test_index

    def _ShowMacrosDefined(self):
        """
        Shows/prints the list of allowed MACROS that can be executed (and information about them)
        """
        macro_index = 1
        for test_key in self.m_user_macros_dict.keys():
            print(" " + str(macro_index) + ". " +
                  self.m_user_macros_dict[test_key][1])
            macro_index = macro_index + 1

        return macro_index

    def _ShowTestsTypes(self):
        """
        Shows/prints the list of allowed tests (and information about them)
        """
        test_index = 1
        for test_key in self.m_protocol_tests_dict.keys():
            test_identifier = int(self.m_protocol_tests_dict[test_key][self.m_prot_manager.SF_HW_TEST_PROTOCOL_MSG_CODE_INDEX])
            print(" " + str(test_index) + ". " +
                  self.m_protocol_tests_dict[test_key][self.m_prot_manager.SF_HW_TEST_PROTOCOL_MSG_COMMENT_INDEX] +
                  " (TEST: " + str(test_identifier).zfill(2) + ")")
            test_index = test_index + 1

        return test_index

    def _ShowSequencesForTests(self):
        """
        Shows/prints the list of allowed sequences of test (and information about them)
        """
        test_index = 1
        for test_key in self.m_protocol_tests_seq_list.keys():
            print(" " + str(test_index) + ". " + self.m_protocol_tests_seq_list[test_key])
            test_index = test_index + 1

        return test_index

    def _ShowPwmsAvailable(self):
        """
        Shows/prints the list of PWMs available for operations (and information about them)
        """
        test_index = 1
        for test_key in self.m_user_pwms_dict.keys():
            print(" " + str(test_index) + ". " +
                  self.m_user_pwms_dict[test_key][self.m_prot_manager.SF_HW_TEST_PROTOCOL_MSG_COMMENT_INDEX])
            test_index = test_index + 1

        return test_index

    def _DefineAndStartFreqSweepMacro(self):
        frequency_command_key = "SF_HW_TEST_PROTOCOL_RQST_SET_PWM_FREQ"
        strinput = self.getInput("Enter start frequency in kHz and press <Enter>: ", "20")
        self.m_macroSweep["start"] = float(strinput)
        strinput = self.getInput("Enter stop frequency in kHz and press <Enter>: ", "30")
        self.m_macroSweep["stop"] = float(strinput)
        steps_amplitude_range = self.m_macroSweep["stop"] - self.m_macroSweep["start"]
        strinput = self.getInput("Enter number of miliseconds for the whole sweep and press <Enter>: ", "3000")
        steps_time_range_in_ms = int(strinput)
        strinput = self.getInput("Enter number of steps of the sweep and press <Enter>: ", "10")
        steps_num = int(strinput)
        if steps_num == 0:
            self.m_macroSweep["step_amplitude"] = steps_amplitude_range
            self.m_macroSweep["step_time_in_ms"] = steps_time_range_in_ms
        else:
            self.m_macroSweep["step_amplitude"] = float(steps_amplitude_range / steps_num)
            self.m_macroSweep["step_time_in_ms"] = int(steps_time_range_in_ms / steps_num)
        if self.m_macroSweep["step_time_in_ms"] == 0:
            self.m_macroSweep["step_time_in_ms"] = 1
        self.m_macroCommandType = frequency_command_key
        self.m_macroInstance = 0
        self.m_macroAsyncTrigger = True
        self.m_macroType = "frequency sweep"

    def _DefineAndStartFreqTrapezoidalMacro(self):
        frequency_command_key = "SF_HW_TEST_PROTOCOL_RQST_SET_PWM_FREQ"
        strinput = self.getInput("Enter start frequency in kHz and press <Enter>: ", "20")
        self.m_macroTrapezoidal["start"] = float(strinput)
        strinput = self.getInput("Enter seattle frequency in kHz and press <Enter>: ", "30")
        self.m_macroTrapezoidal["seattle"] = float(strinput)
        steps_amplitude_range = self.m_macroTrapezoidal["seattle"] - self.m_macroTrapezoidal["start"]
        strinput = self.getInput("Enter number of miliseconds for the rise and press <Enter>: ", "3000")
        steps_time_range_in_ms = int(strinput)
        strinput = self.getInput("Enter number of steps of the rise and press <Enter>: ", "10")
        steps_num = int(strinput)
        if steps_num == 0:
            self.m_macroTrapezoidal["rise_step_amplitude"] = steps_amplitude_range
            self.m_macroTrapezoidal["rise_step_time_in_ms"] = steps_time_range_in_ms
        else:
            self.m_macroTrapezoidal["rise_step_amplitude"] = float(steps_amplitude_range / steps_num)
            self.m_macroTrapezoidal["rise_step_time_in_ms"] = int(steps_time_range_in_ms / steps_num)
        if self.m_macroTrapezoidal["rise_step_time_in_ms"] == 0:
            self.m_macroTrapezoidal["rise_step_time_in_ms"] = 1
        strinput = self.getInput("Enter number of miliseconds during seattle state and press <Enter>: ", "3000")
        self.m_macroTrapezoidal["seattle_time_in_ms"] = int(strinput)
        strinput = self.getInput("Enter stop frequency in kHz and press <Enter>: ", "20")
        self.m_macroTrapezoidal["stop"] = float(strinput)
        steps_amplitude_range = self.m_macroTrapezoidal["stop"] - self.m_macroTrapezoidal["seattle"]
        strinput = self.getInput("Enter number of miliseconds for the fall and press <Enter>: ", "3000")
        steps_time_range_in_ms = int(strinput)
        strinput = self.getInput("Enter number of steps of the fall and press <Enter>: ", "10")
        steps_num = int(strinput)
        if steps_num == 0:
            self.m_macroTrapezoidal["fall_step_amplitude"] = steps_amplitude_range
            self.m_macroTrapezoidal["fall_step_time_in_ms"] = steps_time_range_in_ms
        else:
            self.m_macroTrapezoidal["fall_step_amplitude"] = float(steps_amplitude_range / steps_num)
            self.m_macroTrapezoidal["fall_step_time_in_ms"] = int(steps_time_range_in_ms / steps_num)
        if self.m_macroTrapezoidal["fall_step_time_in_ms"] == 0:
            self.m_macroTrapezoidal["fall_step_time_in_ms"] = 1
        self.m_macroCommandType = frequency_command_key
        self.m_macroInstance = 0
        self.m_macroAsyncTrigger = True
        self.m_macroType = "frequency trapezoidal"

    def _DefineAndStartDutySweepMacro(self):
        duty_command_key = "SF_HW_TEST_PROTOCOL_RQST_SET_PWM_DUTY"
        items_keys = list(self.m_user_pwms_dict.keys())
        number_of_items = self._ShowPwmsAvailable()
        print("")

        strinput = self.getInput("Select PWM and press <Enter>: ", "")
        if strinput != "":
            try:
                selected_item = (int(strinput)) - 1
            except:
                selected_item = number_of_items

            if selected_item < number_of_items:
                strinput = self.getInput("Enter start duty cycle in per units (0.0 to 1.0) and press <Enter>: ",
                                         "0.0")
                self.m_macroSweep["start"] = float(strinput)
                strinput = self.getInput("Enter stop duty cycle in per units (0.0 to 1.0) and press <Enter>: ",
                                         "1.0")
                self.m_macroSweep["stop"] = float(strinput)
                steps_amplitude_range = self.m_macroSweep["stop"] - self.m_macroSweep["start"]
                strinput = self.getInput(
                    "Enter number of miliseconds for the whole sweep and press <Enter>: ", "3000")
                steps_time_range_in_ms = int(strinput)
                strinput = self.getInput("Enter number of steps of the sweep and press <Enter>: ",
                                         "10")
                steps_num = int(strinput)
                if steps_num == 0:
                    self.m_macroSweep["step_amplitude"] = steps_amplitude_range
                    self.m_macroSweep["step_time_in_ms"] = steps_time_range_in_ms
                else:
                    self.m_macroSweep["step_amplitude"] = float(steps_amplitude_range / steps_num)
                    self.m_macroSweep["step_time_in_ms"] = int(steps_time_range_in_ms / steps_num)
                if self.m_macroSweep["step_time_in_ms"] == 0:
                    self.m_macroSweep["step_time_in_ms"] = 1
                self.m_macroCommandType = duty_command_key
                self.m_macroInstance = self.m_user_pwms_dict[items_keys[selected_item]][0]
                self.m_macroAsyncTrigger = True
                self.m_macroType = "dutycycle sweep"
            else:
                print("Invalid pwm selection")

    def _DefineAndStartDutyTrapezoidalMacro(self):
        duty_command_key = "SF_HW_TEST_PROTOCOL_RQST_SET_PWM_DUTY"
        items_keys = list(self.m_user_pwms_dict.keys())
        number_of_items = self._ShowPwmsAvailable()
        print("")

        strinput = self.getInput("Select PWM and press <Enter>: ", "")
        if strinput != "":
            try:
                selected_item = (int(strinput)) - 1
            except:
                selected_item = number_of_items

            if selected_item < number_of_items:
                strinput = self.getInput("Enter start duty cycle in per units (0.0 to 1.0) and press <Enter>: ","0.0")
                self.m_macroTrapezoidal["start"] = float(strinput)
                strinput = self.getInput("Enter seattle duty cycle in per units (0.0 to 1.0) and press <Enter>: ","1.0")
                self.m_macroTrapezoidal["seattle"] = float(strinput)
                steps_amplitude_range = self.m_macroTrapezoidal["seattle"] - self.m_macroTrapezoidal["start"]
                strinput = self.getInput("Enter number of miliseconds for the rise and press <Enter>: ", "3000")
                steps_time_range_in_ms = int(strinput)
                strinput = self.getInput("Enter number of steps of the rise and press <Enter>: ","10")
                steps_num = int(strinput)
                if steps_num == 0:
                    self.m_macroTrapezoidal["rise_step_amplitude"] = steps_amplitude_range
                    self.m_macroTrapezoidal["rise_step_time_in_ms"] = steps_time_range_in_ms
                else:
                    self.m_macroTrapezoidal["rise_step_amplitude"] = float(steps_amplitude_range / steps_num)
                    self.m_macroTrapezoidal["rise_step_time_in_ms"] = int(steps_time_range_in_ms / steps_num)
                if self.m_macroTrapezoidal["rise_step_time_in_ms"] == 0:
                    self.m_macroTrapezoidal["rise_step_time_in_ms"] = 1
                strinput = self.getInput("Enter number of miliseconds during seattle state and press <Enter>: ", "3000")
                self.m_macroTrapezoidal["seattle_time_in_ms"] = int(strinput)
                strinput = self.getInput("Enter stop duty cycle in per units (0.0 to 1.0) and press <Enter>: ","1.0")
                self.m_macroTrapezoidal["stop"] = float(strinput)
                steps_amplitude_range = self.m_macroTrapezoidal["stop"] - self.m_macroTrapezoidal["seattle"]
                strinput = self.getInput("Enter number of miliseconds for the fall and press <Enter>: ", "3000")
                steps_time_range_in_ms = int(strinput)
                strinput = self.getInput("Enter number of steps of the fall and press <Enter>: ","10")
                steps_num = int(strinput)
                if steps_num == 0:
                    self.m_macroTrapezoidal["fall_step_amplitude"] = steps_amplitude_range
                    self.m_macroTrapezoidal["fall_step_time_in_ms"] = steps_time_range_in_ms
                else:
                    self.m_macroTrapezoidal["fall_step_amplitude"] = float(steps_amplitude_range / steps_num)
                    self.m_macroTrapezoidal["fall_step_time_in_ms"] = int(steps_time_range_in_ms / steps_num)
                if self.m_macroTrapezoidal["fall_step_time_in_ms"] == 0:
                    self.m_macroTrapezoidal["fall_step_time_in_ms"] = 1

                self.m_macroCommandType = duty_command_key
                self.m_macroInstance = self.m_user_pwms_dict[items_keys[selected_item]][0]
                self.m_macroAsyncTrigger = True
                self.m_macroType = "dutycycle trapezoidal"
            else:
                print("Invalid pwm selection")

    def _DefineAndStartDeadTimeSweepMacro(self):
        deadtime_command_key = "SF_HW_TEST_CAN_PROTOCOL_CMD_SET_PWM_DT"
        strinput = self.getInput("Enter start dead-time in ns and press <Enter>: ", "500")
        self.m_macroSweep["start"] = float(strinput)
        strinput = self.getInput("Enter stop dead-time in ns and press <Enter>: ", "1000")
        self.m_macroSweep["stop"] = float(strinput)
        steps_amplitude_range = self.m_macroSweep["stop"] - self.m_macroSweep["start"]
        strinput = self.getInput("Enter number of miliseconds for the whole sweep and press <Enter>: ", "3000")
        steps_time_range_in_ms = int(strinput)
        strinput = self.getInput("Enter number of steps of the sweep and press <Enter>: ", "10")
        steps_num = int(strinput)
        if steps_num == 0:
            self.m_macroSweep["step_amplitude"] = steps_amplitude_range
            self.m_macroSweep["step_time_in_ms"] = steps_time_range_in_ms
        else:
            self.m_macroSweep["step_amplitude"] = float(steps_amplitude_range / steps_num)
            self.m_macroSweep["step_time_in_ms"] = int(steps_time_range_in_ms / steps_num)
        if self.m_macroSweep["step_time_in_ms"] == 0:
            self.m_macroSweep["step_time_in_ms"] = 1
        self.m_macroCommandType = deadtime_command_key
        self.m_macroInstance = 0
        self.m_macroAsyncTrigger = True
        self.m_macroType = "deadtime sweep"

    def _DefineAndStartDeadTimeTrapezoidalMacro(self):
        deadtime_command_key = "SF_HW_TEST_CAN_PROTOCOL_CMD_SET_PWM_DT"
        strinput = self.getInput("Enter start dead-time in ns and press <Enter>: ", "500")
        self.m_macroTrapezoidal["start"] = float(strinput)
        strinput = self.getInput("Enter seattle dead-time in ns and press <Enter>: ", "1000")
        self.m_macroTrapezoidal["seattle"] = float(strinput)
        steps_amplitude_range = self.m_macroTrapezoidal["seattle"] - self.m_macroTrapezoidal["start"]
        strinput = self.getInput("Enter number of miliseconds for the rise and press <Enter>: ", "3000")
        steps_time_range_in_ms = int(strinput)
        strinput = self.getInput("Enter number of steps of the rise and press <Enter>: ", "10")
        steps_num = int(strinput)
        if steps_num == 0:
            self.m_macroTrapezoidal["rise_step_amplitude"] = steps_amplitude_range
            self.m_macroTrapezoidal["rise_step_time_in_ms"] = steps_time_range_in_ms
        else:
            self.m_macroTrapezoidal["rise_step_amplitude"] = float(steps_amplitude_range / steps_num)
            self.m_macroTrapezoidal["rise_step_time_in_ms"] = int(steps_time_range_in_ms / steps_num)
        if self.m_macroTrapezoidal["rise_step_time_in_ms"] == 0:
            self.m_macroTrapezoidal["rise_step_time_in_ms"] = 1
        strinput = self.getInput("Enter number of miliseconds during seattle state and press <Enter>: ", "3000")
        self.m_macroTrapezoidal["seattle_time_in_ms"] = int(strinput)
        strinput = self.getInput("Enter stop dead-time in ns and press <Enter>: ", "500")
        self.m_macroTrapezoidal["stop"] = float(strinput)
        steps_amplitude_range = self.m_macroTrapezoidal["stop"] - self.m_macroTrapezoidal["seattle"]
        strinput = self.getInput("Enter number of miliseconds for the fall and press <Enter>: ", "3000")
        steps_time_range_in_ms = int(strinput)
        strinput = self.getInput("Enter number of steps of the fall and press <Enter>: ", "10")
        steps_num = int(strinput)
        if steps_num == 0:
            self.m_macroTrapezoidal["fall_step_amplitude"] = steps_amplitude_range
            self.m_macroTrapezoidal["fall_step_time_in_ms"] = steps_time_range_in_ms
        else:
            self.m_macroTrapezoidal["fall_step_amplitude"] = float(steps_amplitude_range / steps_num)
            self.m_macroTrapezoidal["fall_step_time_in_ms"] = int(steps_time_range_in_ms / steps_num)
        if self.m_macroTrapezoidal["fall_step_time_in_ms"] == 0:
            self.m_macroTrapezoidal["fall_step_time_in_ms"] = 1
        self.m_macroCommandType = deadtime_command_key
        self.m_macroInstance = 0
        self.m_macroAsyncTrigger = True
        self.m_macroType = "deadtime trapezoidal"

    def _ShowDigOutputsAvailable(self):
        """
        Shows/prints the list of PWMs available for operations (and information about them)
        """
        test_index = 1
        for test_key in self.m_user_dig_outs_dict.keys():
            print(" " + str(test_index) + ". " +
                  self.m_user_dig_outs_dict[test_key][self.m_prot_manager.SF_HW_TEST_PROTOCOL_MSG_COMMENT_INDEX])
            test_index = test_index + 1

        return test_index

    def _SendUserRequestByCAN(self, msg_len, msg_payload):
        if not self.APP_HW_TEST_DUMMY_COMMS:
            self.WriteMessage(self.m_protocol_canid, msg_len, msg_payload)
        else:
            print("RQST: (" + str(msg_len) + "): " + self.m_prot_manager.sfHwTestProtocolPrintMessagePayload(msg_payload))

    def _TraceCurrentTimeStamp(self):
        now_ts = datetime.now()

        return str(now_ts.year) + "/" + str(now_ts.month).zfill(2) + "/" + str(now_ts.day).zfill(2) + "  " + str(now_ts.hour).zfill(2) + ":" + str(now_ts.minute).zfill(2) + ":" + str(now_ts.second).zfill(2) + " -> "

    def _TraceGetFileReopenMaskTime(self):
        now_ts = datetime.now()

        return str(now_ts.year) + "/" + str(now_ts.month).zfill(2) + "/" + str(now_ts.day).zfill(2)

    def _TraceMessageToFile(self, user_msg):
        if self.m_logging_traces:
            current_mask = self._TraceGetFileReopenMaskTime()
            if current_mask != self.m_log_time_mask:
                # Closes current file and opens a new one starting from this moment
                self.EnableDisableLogToFile(False)
                self.EnableDisableLogToFile(True)
                self.m_log_time_mask = current_mask

            self.m_log_file_handler.write(user_msg + "\n")

    def _TraceUserMessages(self, user_msg):
        user_msg = self._TraceCurrentTimeStamp() + user_msg
        print(user_msg)
        if self.m_logging_traces:
            self._TraceMessageToFile(user_msg)

    def _TraceReceivedObjects(self, cause):
        objects_string = self._TraceCurrentTimeStamp()
        for object_key in self.m_reported_objects:
            objects_string = (objects_string +
                              self.m_prot_manager.sfHwTestProtocolPrintObject(self.m_reported_objects[object_key]) +
                              "; ")

        if self.m_trace_enabled != self.APP_TRACE_MODE_DISABLED:
            if (cause == self.APP_TRACE_CAUSE_USER_INFO or
                    cause == self.APP_TRACE_CAUSE_OBJECT_ADDED or
                    self.m_trace_enabled == self.APP_TRACE_MODE_ENABLED or
                    (cause == self.APP_TRACE_CAUSE_OBJECT_CHANGE and self.m_trace_enabled == self.APP_TRACE_MODE_ONLY_DIFFERENCE)):
                print(objects_string)
                if self.m_logging_traces:
                    self._TraceMessageToFile(objects_string)

    def _ThreadListeningExecute(self):
        '''
        Thread function for reading messages
        '''
        while self.m_ListeningRun:
            if not self.APP_HW_TEST_DUMMY_COMMS:
                ## time.sleep(0.001) ## Use Sleep to reduce the CPU load
                self.ReadMessages()
            else:
                self._SelfTestReadMessage(8, [0x81, 0x40, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1F])
                time.sleep(1)
                # print("Timer: " + str(time.time()))

        print("Listening thread stopped.")

    def _ThreadSequenceExecute(self):
        '''
        Thread function for execute a sequence of tests
        '''
        while self.m_sequenceRun:
            if self.m_sequenceInProgress:
                # Starts sequence
                if self.m_sequenceState == 0:
                    # Builds the message to configure general state for testing
                    request_payload = self.m_prot_manager.sfHwTestProtocolProcessTxMessage(
                        "SF_HW_TEST_PROTOCOL_RQST_SET_TEST_ENV",
                        0,
                        self.m_prot_manager.SF_HW_TEST_PROTOCOL_TEST_SET_ENV_FLAGS_REPORT_ENABLE)
                    if request_payload:
                        self._SendUserRequestByCAN(request_payload[0], request_payload[1])
                    self.m_sequenceItem = 0
                    self.m_sequenceState = self.m_sequenceState + 1

                # Execute each test in the list
                elif self.m_sequenceState == 1:
                    # Builds the message to set the TEST
                    request_payload = self.m_prot_manager.sfHwTestProtocolProcessTxMessage(
                        "SF_HW_TEST_PROTOCOL_RQST_SET_TEST", 0,
                        self.m_protocol_tests_seq_steps_list[self.m_sequenceItem][self.m_prot_manager.SF_HW_TEST_PROTOCOL_SEQUENCE_ITEM_KEY_INDEX])
                    if request_payload:
                        self._SendUserRequestByCAN(request_payload[0], request_payload[1])
                    self.m_reported_objects.clear()
                    self.m_sequenceItemTimeout = self.m_protocol_tests_seq_steps_list[self.m_sequenceItem][self.m_prot_manager.SF_HW_TEST_PROTOCOL_SEQUENCE_ITEM_TIMOUT_INDEX]
                    self.m_sequenceState = self.m_sequenceState + 1

                # Does a user stimulus (if this tests needs it)
                elif self.m_sequenceState == 2:
                    # Checks if there is any additional stimulus as part of the test
                    stimulus_type = self.m_protocol_tests_seq_steps_list[self.m_sequenceItem][self.m_prot_manager.SF_HW_TEST_PROTOCOL_SEQUENCE_ITEM_STIMULUS_TYPE_INDEX]
                    if stimulus_type != "":
                        stimulus_value = self.m_protocol_tests_seq_steps_list[self.m_sequenceItem][
                            self.m_prot_manager.SF_HW_TEST_PROTOCOL_SEQUENCE_ITEM_STIMULUS_VALUE_INDEX]
                        stimulus_payload = self.m_prot_manager.sfHwTestProtocolProcessTxMessage(stimulus_type, 0, stimulus_value)
                        if stimulus_payload:
                            self._SendUserRequestByCAN(stimulus_payload[0], stimulus_payload[1])
                    self.m_sequenceState = self.m_sequenceState + 1

                # Waits until item test has finished
                elif self.m_sequenceState == 3:
                    self.m_sequenceItemTimeout = self.m_sequenceItemTimeout - self.APP_HW_TEST_SEQ_QUANTUM_TIME_IN_MS
                    if self.m_sequenceItemTimeout <= 0:
                        self.m_sequenceItem = self.m_sequenceItem + 1
                        if self.m_sequenceItem < len(self.m_protocol_tests_seq_steps_list):
                            self.m_sequenceState = self.m_sequenceState - 2
                        else:
                            self.m_sequenceState = self.m_sequenceState + 1

                # Finishes sequence execution
                else:
                    self.m_sequenceInProgress = False
                    self.m_sequenceState = 0
                    self._TraceUserMessages("Sequence iteration finished")
            else:
                if self.m_sequencePeriodicRun:
                    # Checks if it´s time for a SYNC execution of sequence
                    now_timestamp = datetime.now()
                    if self.m_sequencePeriodicNextTimestamp < now_timestamp:
                        if self.m_sequencePeriodicIntervalInMinutes != 0:
                            self.m_sequencePeriodicNextTimestamp = (now_timestamp +
                                                                    timedelta(minutes=self.m_sequencePeriodicIntervalInMinutes))
                        else:
                            self.m_sequencePeriodicNextTimestamp = (now_timestamp +
                                                                    timedelta(seconds=self.m_sequencePeriodicIntervalInSeconds))
                        self.m_sequenceSyncTrigger = True
                        self._TraceUserMessages("Triggers synchronous execution of sequence")

                # Checks if HW TEST sequence should start
                if self.m_sequenceAsyncTrigger or self.m_sequenceSyncTrigger:
                    self.m_sequenceAsyncTrigger = False
                    self.m_sequenceSyncTrigger = False
                    if len(self.m_protocol_tests_seq_steps_list) > 0:
                        self.m_sequenceState = 0
                        self.m_sequenceInProgress = True

            time.sleep(self.APP_HW_TEST_SEQ_QUANTUM_TIME_IN_MS/1000) ## Use Sleep to reduce the CPU load

        print("Sequence thread stopped.")

    def _ThreadMacroExecute(self):
        '''
        Thread function for execute a macro of steps
        '''
        while self.m_macroRun:
            if self.m_macroInProgress:
                # Starts macro
                if self.m_macroState == 0:
                    self.m_macroState = self.APP_HW_TEST_MACRO_INVALID_STEP
                    # Checks which type of MACRO should be executed
                    if self.m_macroType:
                        if (self.m_macroType == "frequency sweep" or
                                self.m_macroType == "dutycycle sweep" or
                                self.m_macroType == "deadtime sweep"):
                            self.m_macroSweep["current"] = self.m_macroSweep["start"]
                            self.m_macroState = 1
                        elif (self.m_macroType == "frequency trapezoidal" or
                                self.m_macroType == "dutycycle trapezoidal" or
                                self.m_macroType == "deadtime trapezoidal"):
                            self.m_macroTrapezoidal["current"] = self.m_macroTrapezoidal["start"]
                            self.m_macroState = 10

                # Executes single step of the SWEEP macro (first step)
                elif self.m_macroState == 1:
                    # Builds the message to set the reference variable
                    request_payload = self.m_prot_manager.sfHwTestProtocolProcessTxMessage(
                        self.m_macroCommandType, self.m_macroInstance,
                        self.m_macroSweep["current"])
                    if request_payload:
                        self._SendUserRequestByCAN(request_payload[0], request_payload[1])
                    self.m_macroStepTimeout = self.m_macroSweep["step_time_in_ms"]
                    self.m_macroState = self.m_macroState + 1

                # Waits until next step to be executed of the macro (or
                # finishes it)
                elif self.m_macroState == 2:
                    self.m_macroStepTimeout = self.m_macroStepTimeout - self.APP_HW_TEST_MACRO_QUANTUM_TIME_IN_MS
                    if self.m_macroStepTimeout <= 0:
                        # Computes next step of the sweep
                        self.m_macroSweep["current"] = self.m_macroSweep["current"] + self.m_macroSweep["step_amplitude"]

                        # Checks if the range of the sweep is in ascending order
                        if self.m_macroSweep["step_amplitude"] > 0:
                            if self.m_macroSweep["current"] <= self.m_macroSweep["stop"]:
                                self.m_macroStepTimeout = self.m_macroSweep["step_time_in_ms"]
                        else:
                            if self.m_macroSweep["current"] >= self.m_macroSweep["stop"]:
                                self.m_macroStepTimeout = self.m_macroSweep["step_time_in_ms"]

                        if self.m_macroStepTimeout > 0:
                            self.m_macroState = self.m_macroState - 1
                        else:
                            self.m_macroState = self.APP_HW_TEST_MACRO_INVALID_STEP

                # Executes single step of the rise part of TRAPEZOIDAL macro (first step)
                elif self.m_macroState == 10:
                    # Builds the message to set the reference variable
                    request_payload = self.m_prot_manager.sfHwTestProtocolProcessTxMessage(
                        self.m_macroCommandType, self.m_macroInstance,
                        self.m_macroTrapezoidal["current"])
                    if request_payload:
                        self._SendUserRequestByCAN(request_payload[0], request_payload[1])
                    self.m_macroStepTimeout = self.m_macroTrapezoidal["rise_step_time_in_ms"]
                    self.m_macroState = self.m_macroState + 1

                # Waits until next step to be executed of rise process
                elif self.m_macroState == 11:
                    self.m_macroStepTimeout = self.m_macroStepTimeout - self.APP_HW_TEST_MACRO_QUANTUM_TIME_IN_MS
                    if self.m_macroStepTimeout <= 0:
                        # Computes next step of the sweep
                        self.m_macroTrapezoidal["current"] = self.m_macroTrapezoidal["current"] + self.m_macroTrapezoidal["rise_step_amplitude"]

                        # Checks if the range of the sweep is in ascending order
                        if self.m_macroTrapezoidal["rise_step_amplitude"] > 0:
                            if self.m_macroTrapezoidal["current"] <= self.m_macroTrapezoidal["seattle"]:
                                self.m_macroStepTimeout = self.m_macroTrapezoidal["rise_step_time_in_ms"]
                        else:
                            if self.m_macroTrapezoidal["current"] >= self.m_macroTrapezoidal["stop"]:
                                self.m_macroStepTimeout = self.m_macroTrapezoidal["rise_step_time_in_ms"]

                        if self.m_macroStepTimeout > 0:
                            self.m_macroState = self.m_macroState - 1
                        else:
                            self.m_macroStepTimeout = self.m_macroTrapezoidal["seattle_time_in_ms"]
                            self.m_macroState = self.m_macroState + 1

                # Waits the settling time of the trapezoidal
                elif self.m_macroState == 12:
                    self.m_macroStepTimeout = self.m_macroStepTimeout - self.APP_HW_TEST_MACRO_QUANTUM_TIME_IN_MS
                    if self.m_macroStepTimeout <= 0:
                        self.m_macroState = self.m_macroState + 1

                # Executes single step of the fall part of TRAPEZOIDAL macro
                elif self.m_macroState == 13:
                    # Builds the message to set the reference variable
                    request_payload = self.m_prot_manager.sfHwTestProtocolProcessTxMessage(
                        self.m_macroCommandType, self.m_macroInstance,
                        self.m_macroTrapezoidal["current"])
                    if request_payload:
                        self._SendUserRequestByCAN(request_payload[0], request_payload[1])
                    self.m_macroStepTimeout = self.m_macroTrapezoidal["fall_step_time_in_ms"]
                    self.m_macroState = self.m_macroState + 1

                # Waits until next step to be executed of rise process
                elif self.m_macroState == 14:
                    self.m_macroStepTimeout = self.m_macroStepTimeout - self.APP_HW_TEST_MACRO_QUANTUM_TIME_IN_MS
                    if self.m_macroStepTimeout <= 0:
                        # Computes next step of the sweep
                        self.m_macroTrapezoidal["current"] = self.m_macroTrapezoidal["current"] + self.m_macroTrapezoidal["fall_step_amplitude"]

                        # Checks if the range of the sweep is in ascending order
                        if self.m_macroTrapezoidal["fall_step_amplitude"] > 0:
                            if self.m_macroTrapezoidal["current"] <= self.m_macroTrapezoidal["stop"]:
                                self.m_macroStepTimeout = self.m_macroTrapezoidal["fall_step_time_in_ms"]
                        else:
                            if self.m_macroTrapezoidal["current"] >= self.m_macroTrapezoidal["stop"]:
                                self.m_macroStepTimeout = self.m_macroTrapezoidal["fall_step_time_in_ms"]

                        if self.m_macroStepTimeout > 0:
                            self.m_macroState = self.m_macroState - 1
                        else:
                            self.m_macroState = self.APP_HW_TEST_MACRO_INVALID_STEP

                # Finishes macro execution
                else:
                    self.m_macroInProgress = False
                    self.m_macroType = None
                    self.m_macroState = 0
                    self._TraceUserMessages("Macro execution finished")
            else:
                # Checks if HW TEST macro should start
                if self.m_macroAsyncTrigger:
                    self.m_macroAsyncTrigger = False
                    self._TraceUserMessages("Starts execution of macro")
                    self.m_macroState = 0
                    self.m_macroInProgress = True

            time.sleep(self.APP_HW_TEST_MACRO_QUANTUM_TIME_IN_MS/1000) ## Use Sleep to reduce the CPU load

        print("Macro thread stopped.")

    def _SelfTestReadMessage(self, msg_len, msg_payload):
        ## Builds a dummy timestamp
        msgTimeStamp = TPCANTimestamp()
        msgTimeStamp.micros = 0
        msgTimeStamp.millis = 0
        msgTimeStamp.millis_overflow = 0

        ## Builds a dummy message
        msgCanMessage = TPCANMsg()
        msgCanMessage.ID = self.m_protocol_canid
        msgCanMessage.LEN = msg_len
        msgCanMessage.MSGTYPE = PCAN_MESSAGE_STANDARD.value
        for i in range(msg_len):
            msgCanMessage.DATA[i] = msg_payload[i]
            pass

        # Process the dummy message
        self.ProcessMessageCan(msgCanMessage, msgTimeStamp)

    def get_tool_information(self):
        return str(self.APP_HW_TEST_VERSION_MAJOR) + "." + str(self.APP_HW_TEST_VERSION_MINOR)

    def startCANCommunicationsHardwareInterface(self):
        ## Checks if PCANBasic.dll is available, if not, the program terminates
        try:
            self.m_objPCANBasic = PCANBasic()
            self.m_DLLFound = True
        except:
            print("Unable to find the library: PCANBasic.dll !")
            self.m_DLLFound = False
            return False

        ## Initialization of the selected channel
        if self.IsFD:
            stsResult = self.m_objPCANBasic.InitializeFD(self.PcanHandle, self.BitrateFD)
        else:
            stsResult = self.m_objPCANBasic.Initialize(self.PcanHandle, self.Bitrate)

        if stsResult != PCAN_ERROR_OK:
            print("Can not initialize. Please check the connections with the interface.")
            self.ShowStatus(stsResult)
            return False

        return True

    def runBlockingSelfManagementOverCAN(self):
        ## Reading messages...
        self.m_objReadThread = threading.Thread(target=self._ThreadListeningExecute, args=())
        self.m_ConsoleRun = True
        self.m_ListeningRun = True
        self.m_objReadThread.start()
        self.m_sequenceThread = threading.Thread(target=self._ThreadSequenceExecute, args=())
        self.m_sequenceRun = True
        self.m_sequenceThread.start()
        self.m_macroThread = threading.Thread(target=self._ThreadMacroExecute, args=())
        self.m_macroRun = True
        self.m_macroThread.start()
        print("Started HW TEST management (listening messages, request sequencing,...)")
        print("")
        while self.m_ConsoleRun:
            self.m_ConsoleRun = self.commandSelector()

        self.m_ListeningRun = False
        self.m_sequenceRun = False
        self.m_macroRun = False
        self.m_objReadThread.join()
        self.m_sequenceThread.join()
        self.m_macroThread.join()

        return True

    # Public functions
    def getUserCommandsDictionary(self):
        return { "help" :              ("h", "Shows this help"),
                 "request":            ("e", "Executes single request"),
                 "macros":             ("m", "Executes a macro"),
                 "select_sequence":    ("k", "Selects sequence of requests for execution"),
                 "start_sequence":     ("s", "Starts execution of a sequence of requests"),
                 "stop_sequence":      ("S", "Stops execution of a sequence of requests"),
                 "start_periodic_seq": ("p", "Start automatic execution of the sequence of requests"),
                 "stop_periodic_seq":  ("P", "Stops automatic execution of the sequence of requests"),
                 "list_requests":      ("r", "Shows lists of requests available"),
                 "list_tests":         ("a", "Shows lists of tests available"),
                 "list_sequences":     ("x", "Shows lists of sequences of tests"),
                 "trace_enable":       ("t", "Enables trace mode showing received objects"),
                 "trace_diff":         ("d", "Enables trace mode showing only changes on received objects"),
                 "trace_disable":      ("T", "Disables trace mode (do not show received objects)"),
                 "log_start":          ("l", "Starts to log activity (messages, objects...) to file"),
                 "log_stop":           ("L", "Stops to log activity to file"),
                 "show_config":        ("c", "Shows current configuration and status"),
                 "quit":               ("q", "Quits the program"),
                 }

    def getPwmsDictionary(self):
        return { "All Phases" : (0x00, "All phases"),
                 "Phase U PWM": (0x01, "Motor Phase U PWM"),
                 "Phase V PWM": (0x02, "Motor Phase V PWM"),
                 "Phase W PWM": (0x03, "Motor Phase W PWM"),
                 }

    def getDigOuputsDictionary(self):
        return { "None":                 (0x00, "Invalid output"),
                 "Discharge internal":   (0x01, "Activation of DC Link internal discharge circuit"),
                 "Discharge external":   (0x02, "Activation of DC Link external discharge circuit"),
                 "Precharge external":   (0x03, "Activation of DC Link external precharge circuit"),
                 "Main external":        (0x04, "Activation of external main contactor for DC Link"),
                 "External pump enable": (0x05, "Activation of external pump"),
                 }

    def getUserMacrosDictionary(self):
        return { "None"                 : (0x00, "No macro to execute"),
                 "frequency sweep"      : (0x01, "Executes frequency sweep"),
                 "dutycycle sweep"      : (0x02, "Executes duty-cycle sweep"),
                 "deadtime sweep"       : (0x03, "Executes dead-time sweep"),
                 "frequency trapezoidal": (0x04, "Executes frequency trapezoidal profile"),
                 "dutycycle trapezoidal": (0x05, "Executes duty-cycle trapezoidal profile"),
                 "deadtime trapezoidal" : (0x06, "Executes dead-time trapezoidal profile"),
                 }

    def getInput(self, msg="Press <Enter> to continue...\n", default=""):
        res = default
        res = input(msg + "\n")
        if len(res) == 0:
            res = default
        return res

    # Main-Functions
    #region
    def ReadMessages(self):
        """
        Function for reading PCAN-Basic messages
        """
        stsResult = PCAN_ERROR_OK
        ## We read at least one time the queue looking for messages. If a message is found, we look again trying to
        ## find more. If the queue is empty or an error occurs, we get out from the do-while statement.
        while (not (stsResult & PCAN_ERROR_QRCVEMPTY)):
            if self.IsFD:
                stsResult = self.ReadMessageFD()
            else:
                stsResult = self.ReadMessage()
            if stsResult != PCAN_ERROR_OK and stsResult != PCAN_ERROR_QRCVEMPTY:
                self.ShowStatus(stsResult)
                return

    def ReadMessage(self):
        """
        Function for reading messages on normal CAN devices

        Returns:
            A TPCANStatus error code
        """
        ## We execute the "Read" function of the PCANBasic
        stsResult = self.m_objPCANBasic.Read(self.PcanHandle)

        if stsResult[0] == PCAN_ERROR_OK:
            ## We show the received message
            self.ProcessMessageCan(stsResult[1], stsResult[2])

        return stsResult[0]

    def ReadMessageFD(self):
        """
        Function for reading messages on FD devices

        Returns:
            A TPCANStatus error code
        """
        ## We execute the "Read" function of the PCANBasic
        stsResult = self.m_objPCANBasic.ReadFD(self.PcanHandle)

        if stsResult[0] == PCAN_ERROR_OK:
            ## We show the received message
            self.ProcessMessageCanFd(stsResult[1],stsResult[2])

        return stsResult[0]

    def WriteMessage(self, can_id, msg_len, msg_payload):
        """
        Function for writing messages on CAN devices

        Returns:
            A TPCANStatus error code
        """
        ## Sends a CAN message with extended ID, and 8 data bytes
        msgCanMessage = TPCANMsg()
        msgCanMessage.ID = can_id
        msgCanMessage.LEN = msg_len
        msgCanMessage.MSGTYPE = PCAN_MESSAGE_STANDARD.value
        for i in range(msg_len):
            msgCanMessage.DATA[i] = msg_payload[i]
            pass
        return self.m_objPCANBasic.Write(self.PcanHandle, msgCanMessage)

    def WriteMessageFD(self, can_id, msg_len, msg_payload):
        """
        Function for writing messages on CAN-FD devices

        Returns:
            A TPCANStatus error code
        """
        ## Sends a CAN-FD message with standard ID, 64 data bytes, and bitrate switch
        msgCanMessageFD = TPCANMsgFD()
        msgCanMessageFD.ID = can_id
        msgCanMessageFD.DLC = msg_len
        msgCanMessageFD.MSGTYPE = PCAN_MESSAGE_FD.value | PCAN_MESSAGE_BRS.value
        for i in range(msg_len):
            msgCanMessageFD.DATA[i] = msg_payload[i]
            pass
        return self.m_objPCANBasic.WriteFD(self.PcanHandle, msgCanMessageFD)

    def ProcessMessageCan(self,msg,itstimestamp):
         """
         Processes a received CAN message

         Parameters:
             msg = The received PCAN-Basic CAN message
             itstimestamp = Timestamp of the message as TPCANTimestamp structure
         """
         microsTimeStamp = (itstimestamp.micros +
                            (1000 * itstimestamp.millis) +
                            (0x100000000 * 1000 * itstimestamp.millis_overflow))

         if msg.ID == self.m_protocol_canid:
             process_result = self.m_prot_manager.sfHwTestProtocolProcessRxMessage(msg.LEN, msg.DATA)

             if process_result:
                 # Process each type of message process result
                 if (process_result[self.m_prot_manager.SF_HW_TEST_PROTOCOL_PROCESSED_ACTION_INDEX] ==
                         self.m_prot_manager.SF_HW_TEST_PROTOCOL_ACTION_UPDATE_OBJECT):
                     objects_received = process_result[self.m_prot_manager.SF_HW_TEST_PROTOCOL_PROCESSED_OBJECT_INDEX]
                     objects_keys = objects_received.keys()
                     for obj_key in objects_keys:
                        if obj_key in self.m_reported_objects:
                            if self.m_prot_manager.sfHwTestProtocolCheckSignificantChangeInObject(
                                    self.m_reported_objects[obj_key],
                                    objects_received[obj_key]):
                                self.m_reported_objects.update(objects_received)
                                trace_condition = self.APP_TRACE_CAUSE_OBJECT_CHANGE
                            else:
                                self.m_reported_objects.update(objects_received)
                                trace_condition = self.APP_TRACE_CAUSE_OBJECT_NO_CHANGE
                        else:
                            self.m_reported_objects.update(objects_received)
                            trace_condition = self.APP_TRACE_CAUSE_OBJECT_ADDED
                        self._TraceReceivedObjects(trace_condition)
                 elif (process_result[self.m_prot_manager.SF_HW_TEST_PROTOCOL_PROCESSED_ACTION_INDEX] ==
                         self.m_prot_manager.SF_HW_TEST_PROTOCOL_ACTION_CLEAR_OBJECTS):
                     # Clears previous reported objects
                     self.m_reported_objects.clear()
                 elif (process_result[self.m_prot_manager.SF_HW_TEST_PROTOCOL_PROCESSED_ACTION_INDEX] ==
                         self.m_prot_manager.SF_HW_TEST_PROTOCOL_ACTION_HANDLE_ERROR):
                     print("Protocol ERROR") # Prints that a protocol error happened
                 elif (process_result[self.m_prot_manager.SF_HW_TEST_PROTOCOL_PROCESSED_ACTION_INDEX] ==
                         self.m_prot_manager.SF_HW_TEST_PROTOCOL_ACTION_DO_NOTHING):
                     # Do nothing
                    pass
                 else:
                     print("Unknown action")
         elif self.m_trace_enabled == self.APP_TRACE_MODE_ENABLED:
             print("Type: " + self.GetTypeString(msg.MSGTYPE))
             print("ID: " + self.GetIdString(msg.ID, msg.MSGTYPE))
             print("Length: " + str(msg.LEN))
             print("Time: " + self.GetTimeString(microsTimeStamp))
             print("Data: " + self.GetDataString(msg.DATA,msg.MSGTYPE))
             print("----------------------------------------------------------")

    def ProcessMessageCanFd(self,msg,itstimestamp):
        """
        Processes a received CAN-FD message

        Parameters:
            msg = The received PCAN-Basic CAN-FD message
            itstimestamp = Timestamp of the message as microseconds (ulong)
        """
        print("Type: " + self.GetTypeString(msg.MSGTYPE))
        print("ID: " + self.GetIdString(msg.ID, msg.MSGTYPE))
        print("Length: " + str(self.GetLengthFromDLC(msg.DLC)))
        print("Time: " + self.GetTimeString(itstimestamp))
        print("Data: " + self.GetDataString(msg.DATA,msg.MSGTYPE))
        print("----------------------------------------------------------")
    #endregion

    def commandSelector(self):
        """
        Function to manage user´s request by console
        """
        finish_app = True

        # Waits for user´s input
        strinput = self.getInput("Select command (press 'h' and <Enter> for help)", "h")
        if len(strinput) > 0:
            strinput = strinput[0]

            # Parse user´s requests
            if strinput == self.m_user_cmds_dict["help"][self.APP_USER_CMDS_SHORTCUT_INDEX]:
                self.ShowCommandsHelp()
            elif strinput == self.m_user_cmds_dict["request"][self.APP_USER_CMDS_SHORTCUT_INDEX]:
                self.ExecuteProtocolRequest()
            elif strinput == self.m_user_cmds_dict["macros"][self.APP_USER_CMDS_SHORTCUT_INDEX]:
                self.ExecuteMacroRequest()
            elif strinput == self.m_user_cmds_dict["select_sequence"][self.APP_USER_CMDS_SHORTCUT_INDEX]:
                self.SelectProtocolSequenceSelection()
            elif strinput == self.m_user_cmds_dict["start_sequence"][self.APP_USER_CMDS_SHORTCUT_INDEX]:
                self.StartExecuteProtocolSequenceRequests(True, False)
            elif strinput == self.m_user_cmds_dict["stop_sequence"][self.APP_USER_CMDS_SHORTCUT_INDEX]:
                self.StartExecuteProtocolSequenceRequests(False, False)
            elif strinput == self.m_user_cmds_dict["start_periodic_seq"][self.APP_USER_CMDS_SHORTCUT_INDEX]:
                self.StartExecuteProtocolSequenceRequests(True, True)
            elif strinput == self.m_user_cmds_dict["stop_periodic_seq"][self.APP_USER_CMDS_SHORTCUT_INDEX]:
                self.StartExecuteProtocolSequenceRequests(False, True)
            elif strinput == self.m_user_cmds_dict["trace_enable"][self.APP_USER_CMDS_SHORTCUT_INDEX]:
                self.EnableDisableTraceReceivedObjects(True, False)
            elif strinput == self.m_user_cmds_dict["trace_diff"][self.APP_USER_CMDS_SHORTCUT_INDEX]:
                self.EnableDisableTraceReceivedObjects(True, True)
            elif strinput == self.m_user_cmds_dict["trace_disable"][self.APP_USER_CMDS_SHORTCUT_INDEX]:
                self.EnableDisableTraceReceivedObjects(False, False)
            elif strinput == self.m_user_cmds_dict["list_requests"][self.APP_USER_CMDS_SHORTCUT_INDEX]:
                self.ShowRequestsTypesHelp()
            elif strinput == self.m_user_cmds_dict["list_tests"][self.APP_USER_CMDS_SHORTCUT_INDEX]:
                self.ShowTestsTypesHelp()
            elif strinput == self.m_user_cmds_dict["list_sequences"][self.APP_USER_CMDS_SHORTCUT_INDEX]:
                self.ShowTestsSequencesHelp()
            elif strinput == self.m_user_cmds_dict["log_start"][self.APP_USER_CMDS_SHORTCUT_INDEX]:
                self.EnableDisableLogToFile(True)
            elif strinput == self.m_user_cmds_dict["log_stop"][self.APP_USER_CMDS_SHORTCUT_INDEX]:
                self.EnableDisableLogToFile(False)
            elif strinput == self.m_user_cmds_dict["show_config"][self.APP_USER_CMDS_SHORTCUT_INDEX]:
                self.ShowCurrentConfiguration()
            elif strinput == self.m_user_cmds_dict["quit"][self.APP_USER_CMDS_SHORTCUT_INDEX]:
                finish_app = False

        return finish_app

    # Help-Functions
    #region
    def ShowSplashScreen(self):
        """
        Shows/prints the configurable parameters for this sample and information about them
        """
        print("=========================================================================================")
        print("|                        Application to manage HW TEST                                  |")
        print("=========================================================================================")
        print(" Enter 'h' for help                                                                     |")
        print("=========================================================================================")
        print("")

    def ShowCommandsHelp(self):
        """
        Shows/prints user commands for the user interface (and information about them)
        """
        print("=========================================================================================")
        print("|                        Application commands for HW TEST                               |")
        print("=========================================================================================")
        print(" (Enter command character and press <Enter>                                             |")
        print("=========================================================================================")
        for command_key in self.m_user_cmds_dict.keys():
            print(" " +
                  self.m_user_cmds_dict[command_key][self.APP_USER_CMDS_SHORTCUT_INDEX] +
                  " : " +
                  self.m_user_cmds_dict[command_key][self.APP_USER_CMDS_COMMENT_INDEX])
        print("")

    def ShowRequestsTypesHelp(self):
        """
        Shows/prints the list of allowed tests (and information about them)
        """
        print("=========================================================================================")
        print("|                         Protocol requests for HW TEST                                 |")
        print("=========================================================================================")
        self._ShowRequestsTypes()
        print("")

    def ShowTestsTypesHelp(self):
        """
        Shows/prints the list of allowed tests (and information about them)
        """
        print("=========================================================================================")
        print("|                           Embedded tests for HW TEST                                  |")
        print("=========================================================================================")
        print(" (Select test execution, select the specified index and press <Enter>                   |")
        print("=========================================================================================")
        self._ShowTestsTypes()
        print("")

    def ShowTestsSequencesHelp(self):
        """
        Shows/prints the list of allowed tests (and information about them)
        """
        print("=========================================================================================")
        print("|                           Embedded tests for HW TEST                                  |")
        print("=========================================================================================")
        print(" (Select sequence for execution, select the specified index and press <Enter>           |")
        print("=========================================================================================")
        self._ShowSequencesForTests()
        print("")

    def EnableDisableTraceReceivedObjects(self, enable, only_differences):
        if enable:
            if only_differences:
                print("Enabling trace changes on received objects")
                self.m_trace_enabled = self.APP_TRACE_MODE_ONLY_DIFFERENCE
            else:
                print("Enabling trace received objects")
                self.m_trace_enabled = self.APP_TRACE_MODE_ENABLED
        else:
            print("Disabling trace received objects")
            self.m_trace_enabled = self.APP_TRACE_MODE_DISABLED

    def EnableDisableLogToFile(self, enable):
        now_ts = datetime.now()

        log_start_timestamp = (str(now_ts.year) + str(now_ts.month).zfill(2) + str(now_ts.day).zfill(2) +
                                   "_" + str(now_ts.hour).zfill(2) + str(now_ts.minute).zfill(2) + str(now_ts.second).zfill(2))

        self.m_log_time_mask = self._TraceGetFileReopenMaskTime()
        if enable:
            if not self.m_logging_traces:
                try:
                    # Builds file name
                    log_file_name= log_start_timestamp + "_log.txt"

                    # Tries to open the file
                    self.m_log_file_handler = open(log_file_name, 'w')
                    self.m_logging_traces = True
                    print("Enabling log traces to file")
                    self._TraceUserMessages("Start logging (" + log_file_name + ")")
                except:
                    print("Error to start log traces to file")
        elif self.m_logging_traces:
            self._TraceUserMessages("Stop logging")
            self.m_logging_traces = False
            self.m_log_file_handler.close()
            print("Disabling log traces to file")

    def SelectProtocolSequenceSelection(self):
        if not self.m_sequenceInProgress:
            print("=========================================================================================")
            print(" Select sequence to be executed with the specified index and press <Enter>               |")
            print("=========================================================================================")
            items_keys = list(self.m_protocol_tests_seq_list.keys())
            number_of_items = self._ShowSequencesForTests()
            print("")

            strinput = self.getInput("Select sequence index and press <Enter> (NOTE: this step doesn't execute the sequence only selects the desired one): ", "")
            if strinput != "":
                try:
                    selected_item = (int(strinput)) - 1
                except:
                    selected_item = number_of_items

                if selected_item < number_of_items:
                    test_key = items_keys[selected_item]

                    # Parse user´s selection
                    if test_key == "TEST_SEQ_MINIMUM_A0_A1_SAMPLE":
                        self.m_protocol_tests_seq_steps_list = self.m_prot_manager.sfHwTestProtocolGetMinimumASampleTestsList()
                    elif test_key == "TEST_SEQ_MINIMUM_B0_SAMPLE":
                        self.m_protocol_tests_seq_steps_list = self.m_prot_manager.sfHwTestProtocolGetMinimumBSampleTestsList()

                    # Prints tests items included on the sequence
                    print("-----------------------------------------------------------------------------------------")
                    print("| Tests included on this sequence                                                       |")
                    print("-----------------------------------------------------------------------------------------")
                    test_index = 1
                    for test_item in self.m_protocol_tests_seq_steps_list:
                        print(" " + str(test_index) + ". " + test_item[self.m_prot_manager.SF_HW_TEST_PROTOCOL_SEQUENCE_ITEM_KEY_INDEX])
                        test_index = test_index + 1
                else:
                    print("Invalid sequence selection")

    def StartExecuteProtocolSequenceRequests(self, is_start, is_periodic):
        if is_start:
            if is_periodic:
                if not self.m_sequencePeriodicRun:
                    try:
                        strinput = self.getInput("Time interval in minutes <y/n>?", "y")
                        if strinput[0] == "y" or strinput[0] == "Y":
                            strinput = self.getInput("Enter time interval in minutes and press <Enter>: ", "1")
                            self.m_sequencePeriodicIntervalInMinutes = int(strinput)
                            self.m_sequencePeriodicIntervalInSeconds = 0
                        else:
                            strinput = self.getInput("Enter time interval in seconds and press <Enter>: ", "30")
                            self.m_sequencePeriodicIntervalInMinutes = 0
                            self.m_sequencePeriodicIntervalInSeconds = int(strinput)
                        # Sets current instance for the next attempt
                        self.m_sequencePeriodicNextTimestamp = datetime.now()
                        self.m_sequencePeriodicRun = True
                        print("HW TEST periodic sequence starts")
                    except:
                        print("Error setting time interval")
                else:
                    print("HW TEST periodic sequence already active")
            elif not self.m_sequenceInProgress:
                self.m_sequenceAsyncTrigger = True
                self._TraceUserMessages("Triggers asynchronous execution of sequence")
            else:
                print("HW TEST sequence already running")
        else:
            if self.m_sequenceInProgress:
                self.m_sequenceInProgress = False
                self._TraceUserMessages("HW TEST sequence stoped")
            if is_periodic:
                self.m_sequencePeriodicRun = False
                print("HW TEST periodic sequence stops")

    def ExecuteProtocolRequest(self):
        """
        Guides the user to select the request to be done
        """
        if not self.m_sequenceInProgress:
            print("=========================================================================================")
            print(" Select request type with the specified index and press <Enter>                         |")
            print("=========================================================================================")
            items_keys = list(self.m_protocol_requests.keys())
            number_of_items = self._ShowRequestsTypes()
            print("")

            default_value = 0
            default_flags = 0
            strinput = self.getInput("Select request index and press <Enter>: ", "")
            if strinput != "":
                try:
                    selected_item = (int(strinput)) - 1
                except:
                    selected_item = number_of_items

                if selected_item < number_of_items:
                    command_key = items_keys[selected_item]
                    can_msg_payload = None

                    if items_keys[selected_item] == "SF_HW_TEST_PROTOCOL_RQST_NOP":   # Hardcoded!!! NOP
                        can_msg_payload = self.m_prot_manager.sfHwTestProtocolProcessTxMessage(command_key, 0, 0)
                    elif items_keys[selected_item] == "SF_HW_TEST_PROTOCOL_RQST_SET_TEST_ENV":  # Hardcoded!!! SET_TEST_ENV
                        strinput = self.getInput("Reset REBOOT flag <y/n>?", "y")
                        if strinput[0] == "y" or strinput[0] == "Y":
                            default_value = default_value | self.m_prot_manager.SF_HW_TEST_PROTOCOL_TEST_SET_ENV_FLAGS_CLEAR_REBOOT
                        strinput = self.getInput("Test should report data by communications <y/n>?", "y")
                        if strinput[0] == "y" or strinput[0] == "Y":
                            default_value = default_value | self.m_prot_manager.SF_HW_TEST_PROTOCOL_TEST_SET_ENV_FLAGS_REPORT_ENABLE
                        can_msg_payload = self.m_prot_manager.sfHwTestProtocolProcessTxMessage(command_key, 0, default_value)
                    elif items_keys[selected_item] == "SF_HW_TEST_PROTOCOL_RQST_SET_TEST":   # Hardcoded!!! SET_TEST
                        items_keys = list(self.m_protocol_tests_dict.keys())
                        number_of_items = self._ShowTestsTypes()
                        print("")

                        strinput = self.getInput("Select request test and press <Enter>: ", "")
                        if strinput != "":
                            try:
                                selected_item = (int(strinput)) - 1
                            except:
                                selected_item = number_of_items

                            if selected_item < number_of_items:
                                test_key = items_keys[selected_item]
                                can_msg_payload = self.m_prot_manager.sfHwTestProtocolProcessTxMessage(command_key, 0, test_key)
                                self.m_reported_objects.clear()
                            else:
                                print("Invalid test selection")
                    elif items_keys[selected_item] == "SF_HW_TEST_PROTOCOL_RQST_ECHO":  # Hardcoded!!! ECHO
                        default_value = 0x55
                        can_msg_payload = self.m_prot_manager.sfHwTestProtocolProcessTxMessage(command_key, 0, default_value)
                    elif items_keys[selected_item] == "SF_HW_TEST_PROTOCOL_RQST_SET_PWM_FREQ":  # Hardcoded!!! SET_FREQ
                        strinput = self.getInput("Single value (y) or macro for sweep range (n) <y/n>?", "y")
                        if strinput[0] == "y" or strinput[0] == "Y":
                            strinput = self.getInput("Enter desired frequency in kHz and press <Enter>: ", "20")
                            default_value = float(strinput)
                            can_msg_payload = self.m_prot_manager.sfHwTestProtocolProcessTxMessage(command_key, 0,
                                                                                               default_value)
                        else:
                            self._DefineAndStartFreqSweepMacro()

                    elif items_keys[selected_item] == "SF_HW_TEST_PROTOCOL_RQST_SET_PWM_DUTY":   # Hardcoded!!! SET_DUTY
                        strinput = self.getInput("Single value (y) or macro for sweep range (n) <y/n>?", "y")
                        if strinput[0] == "y" or strinput[0] == "Y":
                            items_keys = list(self.m_user_pwms_dict.keys())
                            number_of_items = self._ShowPwmsAvailable()
                            print("")

                            strinput = self.getInput("Select PWM and press <Enter>: ", "")
                            if strinput != "":
                                try:
                                    selected_item = (int(strinput)) - 1
                                except:
                                    selected_item = number_of_items

                                if selected_item < number_of_items:

                                        strinput = self.getInput("Enter desired duty cycle (as unitary value, 0.0 to 1.0) and press <Enter>: ", "0.5")
                                        default_value = float(strinput)

                                        can_msg_payload = self.m_prot_manager.sfHwTestProtocolProcessTxMessage(command_key,
                                                                                                               self.m_user_pwms_dict[items_keys[selected_item]][0],
                                                                                                               default_value)
                                        self.m_reported_objects.clear()
                            else:
                                print("Invalid pwm selection")
                        else:
                            self._DefineAndStartDutySweepMacro()

                    elif items_keys[selected_item] == "SF_HW_TEST_CAN_PROTOCOL_CMD_SET_DIG_OUT":   # Hardcoded!!! SET_STATE for digital output
                        items_keys = list(self.m_user_dig_outs_dict.keys())
                        number_of_items = self._ShowDigOutputsAvailable()
                        print("")

                        strinput = self.getInput("Select digital output and press <Enter>: ", "")
                        if strinput != "":
                            try:
                                selected_item = (int(strinput)) - 1
                            except:
                                selected_item = number_of_items

                            if selected_item < number_of_items:
                                strinput = self.getInput("Set output active <y/n>?", "n")
                                if strinput[0] != "y" and strinput[0] != "Y":
                                    default_flags = default_flags | self.m_prot_manager.SF_HW_TEST_PROTOCOL_TEST_SET_DIG_OUT_FLAGS_RESET

                                strinput = self.getInput("Enter pulse duration in ms (0 for permanent state) and press <Enter>: ", "0")
                                default_value = int(strinput)

                                can_msg_payload = self.m_prot_manager.sfHwTestProtocolProcessTxMessage(command_key,
                                                                                                       self.m_user_dig_outs_dict[items_keys[selected_item]][0],
                                                                                                       default_value, default_flags)
                                self.m_reported_objects.clear()
                            else:
                                print("Invalid test selection")
                    elif items_keys[selected_item] == "SF_HW_TEST_CAN_PROTOCOL_CMD_SET_PWM_DT":  # Hardcoded!!! SET_DEADTIME
                        strinput = self.getInput("Single value (y) or macro for sweep range (n) <y/n>?", "y")
                        if strinput[0] == "y" or strinput[0] == "Y":
                            strinput = self.getInput("Enter desired dead-time in ns and press <Enter>: ", "1000")
                            default_value = float(strinput)
                            can_msg_payload = self.m_prot_manager.sfHwTestProtocolProcessTxMessage(command_key, 0, default_value)
                        else:
                            self._DefineAndStartDeadTimeSweepMacro()
                    elif items_keys[selected_item] == "SF_HW_TEST_CAN_PROTOCOL_CMD_SET_PWM_PULSES":  # Hardcoded!!! SET_PWM_PULSES
                        strinput = self.getInput("Enter desired number of pulses (ticks) and press <Enter>: ", "1000")
                        default_value = int(strinput)
                        can_msg_payload = self.m_prot_manager.sfHwTestProtocolProcessTxMessage(command_key,
                                                                                               0,
                                                                                               default_value)
                    elif items_keys[selected_item] == "SF_HW_TEST_CAN_PROTOCOL_CMD_EN_DIS_PHASE":   # Hardcoded!!! SET_EN_DIS_PHASES
                        items_keys = list(self.m_user_pwms_dict.keys())
                        number_of_items = self._ShowPwmsAvailable()
                        print("")

                        strinput = self.getInput("Select PWM and press <Enter>: ", "")
                        if strinput != "":
                            try:
                                selected_item = (int(strinput)) - 1
                            except:
                                selected_item = number_of_items

                            if selected_item < number_of_items:
                                strinput = self.getInput("Enable (y) or disable (n) range <y/n>?", "y")
                                if strinput[0] == "y" or strinput[0] == "Y":
                                    default_value = 1
                                else:
                                    default_value = 0

                                can_msg_payload = self.m_prot_manager.sfHwTestProtocolProcessTxMessage(command_key,
                                                                self.m_user_pwms_dict[items_keys[selected_item]][0],
                                                                default_value)
                            else:
                                print("Invalid pwm selection")
                    elif items_keys[selected_item] == "SF_HW_TEST_PROTOCOL_RQST_SET_PUMP_DUTY":  # Hardcoded!!! SET_PUMP_DUTY
                        strinput = self.getInput("Enter desired duty cycle (as unitary value, 0.0 to 1.0) and press <Enter>: ","0.5")
                        default_value = float(strinput)

                        can_msg_payload = self.m_prot_manager.sfHwTestProtocolProcessTxMessage(
                            command_key,
                            0,
                            default_value)
                        self.m_reported_objects.clear()
                    elif items_keys[selected_item] == "SF_HW_TEST_PROTOCOL_RQST_SET_PUMP_FREQ":  # Hardcoded!!! SET_PUMP_FREQ
                        strinput = self.getInput("Enter desired frequency in kHz and press <Enter>: ", "0.4")
                        default_value = float(strinput)

                        can_msg_payload = self.m_prot_manager.sfHwTestProtocolProcessTxMessage(
                            command_key,
                            0,
                            default_value)
                        self.m_reported_objects.clear()

                    if can_msg_payload:
                        self._SendUserRequestByCAN(can_msg_payload[0], can_msg_payload[1])
                else:
                    print("Selected request is out of range")
        else:
            print("Busy for request execution (another request in progress)")

    def ExecuteMacroRequest(self):
        """
        Guides the user to select the macro to be executed
        """
        if not self.m_sequenceInProgress:
            print("=========================================================================================")
            print(" Select macro type with the specified index and press <Enter>                         |")
            print("=========================================================================================")
            items_keys = list(self.m_user_macros_dict.keys())
            number_of_items = self._ShowMacrosDefined()
            print("")

            default_value = 0
            strinput = self.getInput("Select macro index and press <Enter>: ", "")
            if strinput != "":
                try:
                    selected_item = (int(strinput)) - 1
                except:
                    selected_item = number_of_items

                if selected_item < number_of_items:
                    if items_keys[selected_item] == "frequency sweep":   # Hardcoded!!!
                        self._DefineAndStartFreqSweepMacro()
                    elif items_keys[selected_item] == "dutycycle sweep":  # Hardcoded!!!
                        self._DefineAndStartDutySweepMacro()
                    elif items_keys[selected_item] == "deadtime sweep":  # Hardcoded!!!
                        self._DefineAndStartDeadTimeSweepMacro()
                    elif items_keys[selected_item] == "frequency trapezoidal":  # Hardcoded!!!
                        self._DefineAndStartFreqTrapezoidalMacro()
                    elif items_keys[selected_item] == "dutycycle trapezoidal":  # Hardcoded!!!
                        self._DefineAndStartDutyTrapezoidalMacro()
                    elif items_keys[selected_item] == "deadtime trapezoidal":  # Hardcoded!!!
                        self._DefineAndStartDeadTimeTrapezoidalMacro()

    def ShowCurrentConfiguration(self):
        """
        Shows/prints the configured parameters
        """
        trace_status = "(Unknown)"
        if self.m_trace_enabled == self.APP_TRACE_MODE_ENABLED:
            trace_status = "All traces"
        elif self.m_trace_enabled == self.APP_TRACE_MODE_ONLY_DIFFERENCE:
            trace_status = "Only traces changes"
        elif self.m_trace_enabled == self.APP_TRACE_MODE_DISABLED:
            trace_status = "No traces"

        if self.m_logging_traces:
            log_status = "Logging to file"
        else:
            log_status = "No file logging"

        if self.m_sequenceInProgress:
            seq_status = "Sequence in progress"
        else:
            seq_status = "No sequence"

        if self.m_sequencePeriodicRun:
            per_seq_status = "Periodic in progress (next iteration: )" + str(self.m_sequencePeriodicNextTimestamp)
        else:
            per_seq_status = "No sequence"

        print("Parameter values used")
        print("----------------------")
        print("* PCANHandle: " + self.FormatChannelName(self.PcanHandle))
        print("* IsFD: " + str(self.IsFD))
        print("* Bitrate: " + self.ConvertBitrateToString(self.Bitrate))
        print("* BitrateFD: " + self.ConvertBytesToString(self.BitrateFD))
        print("* Trace level: " + trace_status)
        print("* Log to file: " + log_status)
        print("* Sequence execution: " + seq_status)
        print("* Periodic sequence: " + per_seq_status)
        print("")

    def ShowStatus(self,status):
        """
        Shows formatted status

        Parameters:
            status = Will be formatted
        """
        print("=========================================================================================")
        print(self.GetFormattedError(status))
        print("=========================================================================================")

    def FormatChannelName(self, handle, isFD=False):
        """
        Gets the formated text for a PCAN-Basic channel handle

        Parameters:
            handle = PCAN-Basic Handle to format
            isFD = If the channel is FD capable

        Returns:
            The formatted text for a channel
        """
        handleValue = handle.value
        if handleValue < 0x100:
            devDevice = TPCANDevice(handleValue >> 4)
            byChannel = handleValue & 0xF
        else:
            devDevice = TPCANDevice(handleValue >> 8)
            byChannel = handleValue & 0xFF

        if isFD:
           return ('%s:FD %s (%.2Xh)' % (self.GetDeviceName(devDevice.value), byChannel, handleValue))
        else:
           return ('%s %s (%.2Xh)' % (self.GetDeviceName(devDevice.value), byChannel, handleValue))

    def GetFormattedError(self, error):
        """
        Help Function used to get an error as text

        Parameters:
            error = Error code to be translated

        Returns:
            A text with the translated error
        """
        ## Gets the text using the GetErrorText API function. If the function success, the translated error is returned.
        ## If it fails, a text describing the current error is returned.
        stsReturn = self.m_objPCANBasic.GetErrorText(error,0x09)
        if stsReturn[0] != PCAN_ERROR_OK:
            return "An error occurred. Error-code's text ({0:X}h) couldn't be retrieved".format(error)
        else:
            message = str(stsReturn[1])
            return message.replace("'","",2).replace("b","",1)

    def GetLengthFromDLC(dlc):
        """
        Gets the data length of a CAN message

        Parameters:
            dlc = Data length code of a CAN message

        Returns:
            Data length as integer represented by the given DLC code
        """
        if dlc == 9:
            return 12
        elif dlc == 10:
            return 16
        elif dlc == 11:
            return 20
        elif dlc == 12:
            return 24
        elif dlc == 13:
            return 32
        elif dlc == 14:
            return 48
        elif dlc == 15:
            return 64

        return dlc

    def GetIdString(self, id, msgtype):
        """
        Gets the string representation of the ID of a CAN message

        Parameters:
            id = Id to be parsed
            msgtype = Type flags of the message the Id belong

        Returns:
            Hexadecimal representation of the ID of a CAN message
        """
        if (msgtype & PCAN_MESSAGE_EXTENDED.value) == PCAN_MESSAGE_EXTENDED.value:
            return '%.8Xh' %id
        else:
            return '%.3Xh' %id

    def GetTimeString(self, time):
        """
        Gets the string representation of the timestamp of a CAN message, in milliseconds

        Parameters:
            time = Timestamp in microseconds

        Returns:
            String representing the timestamp in milliseconds
        """
        fTime = time / 1000.0
        return '%.1f' %fTime

    def GetTypeString(self, msgtype):
        """
        Gets the string representation of the type of a CAN message

        Parameters:
            msgtype = Type of a CAN message

        Returns:
            The type of the CAN message as string
        """
        if (msgtype & PCAN_MESSAGE_STATUS.value) == PCAN_MESSAGE_STATUS.value:
            return 'STATUS'

        if (msgtype & PCAN_MESSAGE_ERRFRAME.value) == PCAN_MESSAGE_ERRFRAME.value:
            return 'ERROR'

        if (msgtype & PCAN_MESSAGE_EXTENDED.value) == PCAN_MESSAGE_EXTENDED.value:
            strTemp = 'EXT'
        else:
            strTemp = 'STD'

        if (msgtype & PCAN_MESSAGE_RTR.value) == PCAN_MESSAGE_RTR.value:
            strTemp += '/RTR'
        else:
            if (msgtype > PCAN_MESSAGE_EXTENDED.value):
                strTemp += ' ['
                if (msgtype & PCAN_MESSAGE_FD.value) == PCAN_MESSAGE_FD.value:
                    strTemp += ' FD'
                if (msgtype & PCAN_MESSAGE_BRS.value) == PCAN_MESSAGE_BRS.value:
                    strTemp += ' BRS'
                if (msgtype & PCAN_MESSAGE_ESI.value) == PCAN_MESSAGE_ESI.value:
                    strTemp += ' ESI'
                strTemp += ' ]'

        return strTemp

    def GetDataString(self, data, msgtype):
        """
        Gets the data of a CAN message as a string

        Parameters:
            data = Array of bytes containing the data to parse
            msgtype = Type flags of the message the data belong

        Returns:
            A string with hexadecimal formatted data bytes of a CAN message
        """
        if (msgtype & PCAN_MESSAGE_RTR.value) == PCAN_MESSAGE_RTR.value:
            return "Remote Request"
        else:
            strTemp = b""
            for x in data:
                strTemp += b'%.2X ' % x
            return str(strTemp).replace("'","",2).replace("b","",1)

    def GetDeviceName(self, handle):
        """
        Gets the name of a PCAN device

        Parameters:
            handle = PCAN-Basic Handle for getting the name

        Returns:
            The name of the handle
        """
        switcher = {
            PCAN_NONEBUS.value: "PCAN_NONEBUS",
            PCAN_PEAKCAN.value: "PCAN_PEAKCAN",
            PCAN_DNG.value: "PCAN_DNG",
            PCAN_PCI.value: "PCAN_PCI",
            PCAN_USB.value: "PCAN_USB",
            PCAN_VIRTUAL.value: "PCAN_VIRTUAL",
            PCAN_LAN.value: "PCAN_LAN"
        }

        return switcher.get(handle,"UNKNOWN")

    def ConvertBitrateToString(self, bitrate):
        """
        Convert bitrate c_short value to readable string

        Parameters:
            bitrate = Bitrate to be converted

        Returns:
            A text with the converted bitrate
        """
        m_BAUDRATES = {PCAN_BAUD_1M.value:'1 MBit/sec', PCAN_BAUD_800K.value:'800 kBit/sec', PCAN_BAUD_500K.value:'500 kBit/sec', PCAN_BAUD_250K.value:'250 kBit/sec',
                       PCAN_BAUD_125K.value:'125 kBit/sec', PCAN_BAUD_100K.value:'100 kBit/sec', PCAN_BAUD_95K.value:'95,238 kBit/sec', PCAN_BAUD_83K.value:'83,333 kBit/sec',
                       PCAN_BAUD_50K.value:'50 kBit/sec', PCAN_BAUD_47K.value:'47,619 kBit/sec', PCAN_BAUD_33K.value:'33,333 kBit/sec', PCAN_BAUD_20K.value:'20 kBit/sec',
                       PCAN_BAUD_10K.value:'10 kBit/sec', PCAN_BAUD_5K.value:'5 kBit/sec'}
        return m_BAUDRATES[bitrate.value]

    def ConvertBytesToString(self, bytes):
        """
        Convert bytes value to string

        Parameters:
            bytes = Bytes to be converted

        Returns:
            Converted bytes value as string
        """
        return str(bytes).replace("'","",2).replace("b","",1)
    #endregion

if __name__ == "__main__":
    # Creates an instance of the "HW Test" manager
    HwTestManager = InvGen3HardwareTestOverCAN()

    # Print simulator's parameters
    print('Tool version: ' + str(HwTestManager.get_tool_information()))

    # Executes "HW Test" manager over CAN communications
    exit(HwTestManager.runBlockingSelfManagementOverCAN())


