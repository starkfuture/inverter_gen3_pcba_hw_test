## Needed Imports
import struct

class sfHwTestProtocol():

    # Defines
    #region
    SF_HW_TEST_PROTOCOL_VERSION = 0.1

    SF_HW_TEST_PROTOCOL_CANID = 0x100

    # Message payload object format
    # - Object type (analog, digital, status...)
    # - Object value definition (data type) and object identifier (analog channel, digital output...)
    # - Object value field (nothing, float, uint32, buffer...)
    # - Object flags
    SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_EMPTY = 0
    SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_FLOAT = 1
    SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_UINT32 = 2
    SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_BOOL = 3
    SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_BUFFER = 4

    SF_HW_TEST_PROTOCOL_FRAME_COMMAND_INDEX = 0
    SF_HW_TEST_PROTOCOL_FRAME_OBJECT_INFO_INDEX = 1
    SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX = 2
    SF_HW_TEST_PROTOCOL_FRAME_OBJECT_FLAGS_INDEX = 6
    SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_SIZE = 4
    SF_HW_TEST_PROTOCOL_FRAME_OBJECT_FLAGS_SIZE = 2

    # Internal objects format (parsed from/to frame objects)
    SF_HW_TEST_PROTOCOL_OBJECT_TYPE_KEY = "Type"
    SF_HW_TEST_PROTOCOL_OBJECT_FIELD_TEST_TYPE_KEY = "Test_type"
    SF_HW_TEST_PROTOCOL_OBJECT_FIELD_TEST_STATUS_KEY = "Test_status"
    SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_ID_KEY = "Analog_id"
    SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_VALUE_KEY = "Analog_value"
    SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_FLAGS_KEY = "Analog_flags"
    SF_HW_TEST_PROTOCOL_OBJECT_FIELD_BUFFER_VALUE_KEY = "Buffer_value"

    SF_HW_TEST_PROTOCOL_OBJECT_TYPE_NONE = "None"
    SF_HW_TEST_PROTOCOL_OBJECT_TYPE_TEST = "test_info"
    SF_HW_TEST_PROTOCOL_OBJECT_TYPE_ANALOG = "analog_info"
    SF_HW_TEST_PROTOCOL_OBJECT_TYPE_BUFFER = "buffer_info"

    SF_HW_TEST_PROTOCOL_TEST_SET_ENV_FLAGS_CLEAR_REBOOT = 0x01
    SF_HW_TEST_PROTOCOL_TEST_SET_ENV_FLAGS_REPORT_ENABLE = 0x02

    SF_HW_TEST_PROTOCOL_TEST_SET_DIG_OUT_FLAGS_RESET = 0x01

    SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_REBOOT = 0x01
    SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_RUNNING = 0x02
    SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_VERIF = 0x04
    SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_VERIF_OK = 0x08
    SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_SELFTEST = 0x10
    SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_SELFTEST_OK = 0x20

    SF_HW_TEST_PROTOCOL_ANLG_STATUS_OBJ_FLAGS_BITMASK_OUT_OF_RANGE = 0x01
    SF_HW_TEST_PROTOCOL_ANLG_STATUS_OBJ_FLAGS_BITMASK_EXT_ID_BIT0 = 0x02
    SF_HW_TEST_PROTOCOL_ANLG_STATUS_OBJ_FLAGS_BITMASK_EXT_ID_BIT1 = 0x04

    SF_HW_TEST_PROTOCOL_MSG_CODE_INDEX = 0
    SF_HW_TEST_PROTOCOL_MSG_COMMENT_INDEX = 1

    SF_HW_TEST_PROTOCOL_SEQUENCE_COMMENT_INDEX = 0

    SF_HW_TEST_PROTOCOL_SEQUENCE_ITEM_KEY_INDEX = 0
    SF_HW_TEST_PROTOCOL_SEQUENCE_ITEM_STIMULUS_TYPE_INDEX = 1
    SF_HW_TEST_PROTOCOL_SEQUENCE_ITEM_STIMULUS_VALUE_INDEX = 2
    SF_HW_TEST_PROTOCOL_SEQUENCE_ITEM_TIMOUT_INDEX = 3

    SF_HW_TEST_PROTOCOL_LEN_MSG = 8

    SF_HW_TEST_PROTOCOL_PROCESSED_ACTION_INDEX = 0
    SF_HW_TEST_PROTOCOL_PROCESSED_OBJECT_INDEX = 1

    SF_HW_TEST_PROTOCOL_ACTION_DO_NOTHING = 0
    SF_HW_TEST_PROTOCOL_ACTION_HANDLE_ERROR = 1
    SF_HW_TEST_PROTOCOL_ACTION_CLEAR_OBJECTS = 2
    SF_HW_TEST_PROTOCOL_ACTION_UPDATE_OBJECT = 3

    SF_HW_TEST_PROTOCOL_REQUEST_CODE_INDEX = 0
    SF_HW_TEST_PROTOCOL_REQUEST_COMMENT_INDEX = 1
    #endregion

    # Members
    #region

    #endregion

    def __init__(self):
        ## Initialization of dictionaries
        self.protocol_version = self.SF_HW_TEST_PROTOCOL_VERSION
        self.tests_dict = self.sfHwTestProtocolGetTestsDictionary()
        self.request_dict = self.sfHwTestProtocolGetRequestsDictionary()
        self.response_dict = self.sfHwTestProtocolGetResponsesDictionary()

    # Private functions
    def _sfHwTestProtocolObjectFlagsByCommand(self, command, obj_flags):
        """
        Returns a string with flags parsed for the object (depending on command)

        Parameters:
            command: The command within the object is involved
            obj_flags Object flags corresponding to a HW Test protocol object
        """
        obj_string = ""

        if command == self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_TEST:
            if (obj_flags & self.SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_REBOOT) != 0:
                obj_string = " BT"
            if (obj_flags & self.SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_RUNNING) != 0:
                obj_string = obj_string + " RN"
            if (obj_flags & self.SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_VERIF) != 0:
                if (obj_flags & self.SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_VERIF_OK) != 0:
                    obj_string = obj_string + " V+"
                else:
                    obj_string = obj_string + " V-"
            if (obj_flags & self.SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_SELFTEST) != 0:
                if (obj_flags & self.SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_SELFTEST_OK) != 0:
                    obj_string = obj_string + " S+"
                else:
                    obj_string = obj_string + " S-"
        elif command == self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_ANALOG:
            if(obj_flags != 0):
                obj_string = " *"
            else:
                obj_string = ""
        elif command == self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_BUFFER:
            obj_string = hex(obj_flags)

        return obj_string

    def _sfHwTestProtocolProcessTxObject(self, command, obj_type, obj_instance, obj_value, obj_flags):
        """
        Builds a message with the object in the format to include on a protocol frame

        Parameters:
            obj_type = Data type of the value for the object
            obj_instance = Identifier of the object in the system
            obj_value = Value of the object
            obj_flags = Flags of the object
        """
        msg_len = 0
        msg_payload = [0] * self.SF_HW_TEST_PROTOCOL_LEN_MSG

        # Fills value and flags depending on its data type
        if obj_type == self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_EMPTY:
            msg_len = self.SF_HW_TEST_PROTOCOL_LEN_MSG
        elif obj_type == self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_FLOAT:
            msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX:
                        (self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX +
                        self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_SIZE)] = bytearray(struct.pack("<f", obj_value))
            msg_len = self.SF_HW_TEST_PROTOCOL_LEN_MSG
        elif obj_type == self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_UINT32:
            msg_len = self.SF_HW_TEST_PROTOCOL_LEN_MSG
            msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX:
                        (self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX +
                         self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_SIZE)] = obj_value.to_bytes(self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_SIZE, byteorder='big')
        elif obj_type == self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_BOOL:
            msg_len = self.SF_HW_TEST_PROTOCOL_LEN_MSG
            if obj_value:
                bool_value = 1
            else:
                bool_value = 0
            msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX:
                        (self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX +
                         self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_SIZE)] = bool_value.to_bytes(self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_SIZE, byteorder='big')
        elif obj_type == self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_BUFFER:
            msg_len = self.SF_HW_TEST_PROTOCOL_LEN_MSG
            msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX:
                        (self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX +
                         self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_SIZE)] = obj_value[0:self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_SIZE]

        # fills object information and flags
        if msg_len > 0:
            msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_COMMAND_INDEX] = self.request_dict[command][self.SF_HW_TEST_PROTOCOL_MSG_CODE_INDEX]
            msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_INFO_INDEX] = ((obj_type & 0x7) << 5) | (obj_instance & 0x1F)
            msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_FLAGS_INDEX:
                        (self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_FLAGS_INDEX +
                         self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_FLAGS_SIZE)] = obj_flags.to_bytes(self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_FLAGS_SIZE, byteorder='big')

        return [msg_len, msg_payload]

    def _sfHwTestProtocolProcessRxReportNone(self, msg_len, msg_payload):
        """
        Processes a received CAN message of HW Test reporting no value

        Parameters:
            msg_len = Length of the message
            msg_payload = The received payload of the message
        """
        if msg_len == 8:
            ret_action = (self.SF_HW_TEST_PROTOCOL_ACTION_CLEAR_OBJECTS, {})
        else:
            ret_action = (self.SF_HW_TEST_PROTOCOL_ACTION_HANDLE_ERROR, {})
        return ret_action

    def _sfHwTestProtocolProcessRxReportTestStatus(self, msg_len, msg_payload):
        """
        Processes a received CAN message of HW Test status

        Parameters:
            msg_len = Length of the message
            msg_payload = The received payload of the message
        """
        ret_action = (self.SF_HW_TEST_PROTOCOL_ACTION_HANDLE_ERROR, {})

        if msg_len >= 8:
            # Gets data from the received frame
            raw_bytes = bytes([int(x) for x in msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX:
                                                            (self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX +
                                                            self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_SIZE)]])
            raw_bytes =  raw_bytes + bytes([0] * (4 - self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_SIZE))
            test_value = struct.unpack("<i", raw_bytes)

            raw_bytes = bytes([int(x) for x in msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_FLAGS_INDEX:
                                                           (self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_FLAGS_INDEX +
                                                            self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_FLAGS_SIZE)]])
            raw_bytes = raw_bytes + bytes([0] * (4 - self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_FLAGS_SIZE))
            test_status = struct.unpack("<i", raw_bytes)

            # Builds an object with the information received
            object_info = {(str(self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_TEST) + "0"):
                               {self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_KEY: self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_TEST,
                                self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_TEST_TYPE_KEY: test_value,
                                self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_TEST_STATUS_KEY: test_status}
                           }

            # Defines the action to applied to received object
            ret_action = (self.SF_HW_TEST_PROTOCOL_ACTION_UPDATE_OBJECT, object_info)

        return ret_action

    def _sfHwTestProtocolProcessRxReportAnalog(self, msg_len, msg_payload):
        """
        Processes a received CAN message of HW Test reporting an analog value
        adding or replacing corresponding key on the dictionary

        Parameters:
            msg_len = Length of the message
            msg_payload = The received payload of the message
        """
        ret_action = (self.SF_HW_TEST_PROTOCOL_ACTION_HANDLE_ERROR, {})
        if msg_len >= 8:
            # Gets object definition from the received frame
            analog_obj_info = msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_INFO_INDEX]
            analog_obj_type = (analog_obj_info >> 5) & 0x07

            analog_obj_value = bytes([int(x) for x in msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX:
                                                                    (self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX +
                                                                    self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_SIZE)]])
            analog_obj_value = analog_obj_value + bytes([0] * (4 - self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_SIZE))

            analog_id = analog_obj_info & 0x1F

            analog_obj_flags = bytes([int(x) for x in msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_FLAGS_INDEX:
                                                           (self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_FLAGS_INDEX +
                                                            self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_FLAGS_SIZE)]])
            analog_obj_flags = analog_obj_flags + bytes([0] * (4 - self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_FLAGS_SIZE))
            analog_flags = struct.unpack("<i",analog_obj_flags)
            analog_flags_uint = analog_flags[0]
            if (analog_flags_uint & self.SF_HW_TEST_PROTOCOL_ANLG_STATUS_OBJ_FLAGS_BITMASK_EXT_ID_BIT0) != 0:
                analog_flags_uint = analog_flags_uint & (~self.SF_HW_TEST_PROTOCOL_ANLG_STATUS_OBJ_FLAGS_BITMASK_EXT_ID_BIT0)
                analog_id = analog_id + 0x20
            if (analog_flags_uint & self.SF_HW_TEST_PROTOCOL_ANLG_STATUS_OBJ_FLAGS_BITMASK_EXT_ID_BIT1) != 0:
                analog_flags_uint = analog_flags_uint & (~self.SF_HW_TEST_PROTOCOL_ANLG_STATUS_OBJ_FLAGS_BITMASK_EXT_ID_BIT1)
                analog_id = analog_id + 0x40

            analog_value = None
            if analog_obj_type == self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_FLOAT:
                # Gets data from the received frame
                analog_value = struct.unpack("<f", analog_obj_value)
            elif analog_obj_type == self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_UINT32:
                # Gets data from the received frame
                analog_value = struct.unpack("<i", analog_obj_value)

            if analog_value is not None:
                # Builds an object with the information received
                object_info = {(str(self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_ANALOG) + str(analog_id)):
                               {self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_KEY: self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_ANALOG,
                                self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_ID_KEY: analog_id,
                                self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_VALUE_KEY: analog_value[0],
                                self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_FLAGS_KEY: analog_flags_uint}}

                # Defines the action to be applied to received object
                ret_action = (self.SF_HW_TEST_PROTOCOL_ACTION_UPDATE_OBJECT, object_info)

        return ret_action

    def _sfHwTestProtocolProcessRxReportEcho(self, msg_len, msg_payload):
        """
        Processes a received CAN message of HW Test reporting an echo of
        latest ECHO Request

        Parameters:
            msg_len = Length of the message
            msg_payload = The received payload of the message
        """
        ret_action = (self.SF_HW_TEST_PROTOCOL_ACTION_HANDLE_ERROR, {})
        if msg_len >= 8:
            # Gets object definition from the received frame
            buffer_obj_info = msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_INFO_INDEX]
            buffer_obj_type = (buffer_obj_info >> 5) & 0x07
            buffer_obj_value = bytes([int(x) for x in msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX:
                                                                    (self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX +
                                                                    self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_SIZE)]])

            if buffer_obj_type == self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_BUFFER:
                # Builds an object with the information received
                object_info = {str(self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_BUFFER):
                               {self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_KEY: self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_BUFFER,
                                self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_BUFFER_VALUE_KEY: buffer_obj_value}}

                # Defines the action to be applied to received object
                ret_action = (self.SF_HW_TEST_PROTOCOL_ACTION_UPDATE_OBJECT, object_info)

        return ret_action

    def _sfHwTestProtocolProcessRxReportBuffer(self, msg_len, msg_payload):
        """
        Processes a received CAN message of HW Test reporting a user buffer

        Parameters:
            msg_len = Length of the message
            msg_payload = The received payload of the message
        """
        ret_action = (self.SF_HW_TEST_PROTOCOL_ACTION_HANDLE_ERROR, {})
        if msg_len >= 8:
            # Gets object definition from the received frame
            buffer_obj_info = msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_INFO_INDEX]
            buffer_obj_type = (buffer_obj_info >> 5) & 0x07
            buffer_obj_value = bytes([int(x) for x in msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX:
                                                                    (self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX +
                                                                    self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_SIZE)]])

            if buffer_obj_type == self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_BUFFER:
                # Builds an object with the information received
                object_info = {str(self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_BUFFER):
                               {self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_KEY: self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_BUFFER,
                                self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_BUFFER_VALUE_KEY: buffer_obj_value}}

                # Defines the action to be applied to received object
                ret_action = (self.SF_HW_TEST_PROTOCOL_ACTION_UPDATE_OBJECT, object_info)

        return ret_action

    # Public functions
    def sfHwTestProtocolGetCANid(self):
        """
        Returns the CAN-ID used for the HW Test protocol when it is used over
        CAN bus interface

        Parameters:
        """
        return self.SF_HW_TEST_PROTOCOL_CANID

    def sfHwTestProtocolGetRequestsDictionary(self):
        """
        Returns a dictionary with all allowed request types on the protocol

        Parameters:
        """
        return {
           "SF_HW_TEST_PROTOCOL_RQST_NOP":               (0x00, "Do nothing"),
           "SF_HW_TEST_PROTOCOL_RQST_SET_TEST_ENV":      (0x01, "Selects general configuration for Tests execution"),
           "SF_HW_TEST_PROTOCOL_RQST_SET_TEST":          (0x02, "Switches to the specified Test"),
           "SF_HW_TEST_PROTOCOL_RQST_ECHO":              (0x03, "Message to do an ECHO (if echo test is in progress)"),
           "SF_HW_TEST_PROTOCOL_RQST_SET_PWM_FREQ":      (0x04, "Message to set working frequency (applies only in some tests)"),
           "SF_HW_TEST_PROTOCOL_RQST_SET_PWM_DUTY":      (0x05, "Message to set working duty cycle (applies only in some tests)"),
           "SF_HW_TEST_CAN_PROTOCOL_CMD_SET_DIG_OUT":    (0x06, "Message to set working digital output status (applies only in some tests)"),
           "SF_HW_TEST_CAN_PROTOCOL_CMD_SET_PWM_DT":     (0x07, "Message to set working deadtime on PWMs (applies only in some tests)"),
           "SF_HW_TEST_CAN_PROTOCOL_CMD_SET_PWM_PULSES": (0x08, "Message to set working PWMs pulses/ticks (applies only in some tests)"),
           "SF_HW_TEST_CAN_PROTOCOL_CMD_EN_DIS_PHASE":   (0x09, "Message to enable or disable PWM branches (applies only in some tests)"),
           "SF_HW_TEST_PROTOCOL_RQST_SET_PUMP_DUTY":     (0x0A, "Message to set pump working duty cycle (applies only in some tests)"),
           "SF_HW_TEST_PROTOCOL_RQST_SET_PUMP_FREQ":     (0x0B, "Message to set pump pwm frequency (applies only in some tests)"),
        }

    def sfHwTestProtocolGetResponsesDictionary(self):
        """
        Returns a dictionary with all allowed response types on the protocol

        Parameters:
        """
        return {
           "SF_HW_TEST_PROTOCOL_RSPN_NONE":          (0x80, "Reports nothing"),
           "SF_HW_TEST_PROTOCOL_RSPN_TEST_STATUS":   (0x81, "Test selected and its current status"),
           "SF_HW_TEST_PROTOCOL_RSPN_ANALOG":        (0x82, "Analog value reported"),
           "SF_HW_TEST_PROTOCOL_RSPN_ECHO":          (0x83, "Message echoed related to corresponding ECHO request"),
           "SF_HW_TEST_PROTOCOL_RSPN_BUFFER":        (0x84, "Message with a user buffer"),
        }

    def sfHwTestProtocolGetTestsDictionary(self):
        """
        Returns a dictionary with all allowed tests on the protocol

        Parameters:
        """
        return {
           "HW_TEST_NO_TEST":                       (0x00, "Do not execute any hardware test "),
           "HW_TEST_LEDS":                          (0x01, "Test LEDs continuous "),
           "HW_TEST_SUPPLY_VOLTAGES":               (0x02, "Test that supply voltages(12 V, 5 V...) are right"),
           "HW_TEST_ALL_ADC_MEASUREMENTS":          (0x03, "All measures connected to internal ADCs (also reports them by CAN)"),
           "HW_TEST_MCU_INTER_MEASUREMENTS":        (0x04, "MCU internal measurements (Tcore, Vcore, Vbat and Vref)"),
           "HW_TEST_PWM_DRIVERS_USER_MEASUREMENTS": (0x05, "All measures connected to the isolated ADC included on each internal ADCs (also reports them by CAN)"),
           "HW_TEST_MOTOR_TEMPERATURE_LOOPBACK":    (0x06, "All MOTOR temperature measurements"),
           "HW_TEST_CAPS_TEMPERATURE_LOOPBACK":     (0x07, "All CAPACITORS temperature measurements"),
           "HW_TEST_MEASUREMENTS_DIAGNOSTICS":      (0x08, "External measurements signal integrity and/or quality"),
           "HW_TEST_PWM1_SUPPLY":                   (0x09, "PWM1 power enabling "),
           "HW_TEST_PWM2_SUPPLY":                   (0x0A, "PWM2 power enabling"),
           "HW_TEST_PWM3_SUPPLY":                   (0x0B, "PWM3 power enabling"),
           "HW_TEST_ALL_PWM_SUPPLIES":              (0x0C, "Setting all power supplies simultaneously"),
           "HW_TEST_PWM1_DRIVER_STATUS":            (0x0D, "PWM1 driver status checking for different situations"),
           "HW_TEST_PWM2_DRIVER_STATUS":            (0x0E, "PWM2 driver status checking for different situations"),
           "HW_TEST_PWM3_DRIVER_STATUS":            (0x0F, "PWM3 driver status checking for different situations"),
           "HW_TEST_ALL_DRIVERS_STATUS":            (0x10, "Setting all drivers checking status "),
           "HW_TEST_PWM1_DRIVER_SETTING":           (0x11, "PWM1 driver management"),
           "HW_TEST_PWM2_DRIVER_SETTING":           (0x12, "PWM2 driver management"),
           "HW_TEST_PWM3_DRIVER_SETTING":           (0x13, "PWM3 driver management"),
           "HW_TEST_ALL_DRIVERS_SETTING":           (0x14, "Setting all drivers simultaneously"),
           "HW_TEST_PWM1_SETTING":                  (0x15, "PWM1 settings"),
           "HW_TEST_PWM2_SETTING":                  (0x16, "PWM2 settings"),
           "HW_TEST_PWM3_SETTING":                  (0x17, "PWM3 settings"),
           "HW_TEST_ALL_DRIVERS_FREQUENCY":         (0x18, "Setting freq settings all pwms simultaneously"),
           "HW_TEST_ALL_DRIVERS_DUTY":              (0x19, "Setting duty-cycle settings all pwms simultaneously"),
           "HW_TEST_ALL_DRIVERS_DEADTIME":          (0x1A, "Setting dead-time settings all pwms simultaneously"),
           "HW_TEST_ALL_POWER_MODULE":              (0x1B, "Setting all power branches (drivers and PWMs) simultaneously"),
           "HW_TEST_DISCHARGE_AUTO_CIRCUIT":        (0x1C, "Discharge circuit continuous test"),
           "HW_TEST_CAN_AUTO_TX":                   (0x1D, "CAN continuous transmission and reception "),
           "HW_TEST_CAN_ECHO":                      (0x1E, "CAN echo (transmits what receives)"),
           "HW_TEST_UART_AUTO_TX":                  (0x1F, "UART continuous transmission and reception"),
           "HW_TEST_UART_ECHO":                     (0x20, "UART echo (transmits what receives) "),
           "HW_TEST_UART_CHECK_LOOPBACK":           (0x21, "UART transmits and checks echo received"),
           "HW_TEST_I2C_TEMP_HUMID_AUTO_TX":        (0x22, "External temperature/humidity sensor (through I2C sensor) polling (continuously)"),
           "HW_TEST_SPI_FLASH_MEM_AUTO_TX":         (0x23, "External FLASH SPI executes representatives transactions (continuously)"),
           "HW_TEST_ENC_SPI_AUTO_TX":               (0x24, "Encoder SPI executes representatives transactions (continuously)"),
           "HW_TEST_ENC_SINCOS_SIN_LOOPBACK":       (0x25, "Encoder SIN differential input of SIN-COS analog front-end (input range, Common mode...)"),
           "HW_TEST_ENC_SINCOS_COS_LOOPBACK":       (0x26, "Encoder COS differential input of SIN-COS analog front-end (input range, Common mode...)"),
           "HW_TEST_ENC_ABI_LOOPBACK":              (0x27, "Encoder ABI automatic testing (continuously)"),
           "HW_TEST_DAC_OUT_AUTO":                  (0x28, "DAC continuous output waveform"),
           "HW_TEST_EXTRA_GPIOs_LOOPBACK":          (0x29, "Test extra GPIOs loopback"),
           "HW_TEST_POWER_UNIPLR_V_LOOPBACK":       (0x2A, "Loopbacks from DACs to isolated inputs of power unipolar voltage measurements"),
           "HW_TEST_POWER_BIPLR_V_LOOPBACK":        (0x2B, "Loopbacks from DACs to isolated inputs of power bipolar voltage measurements"),
           "HW_TEST_DCLINK_MANAGEMENT":             (0x2C, "Manages DC-Link state (external precharge/main-relay conmutation, internal/external discharge...)"),
           "HW_TEST_POWER_MODULES_BY_PULSES":       (0x2D, "Setting all power branches (drivers and PWMs) simultaneously only for a finite number of pulses/ticks"),
           "HW_TEST_EXT_TEMPERATURE_LOOPBACK":      (0x2E, "All external input temperature measurements input range using a loopback with internal DACs"),
           "HW_TEST_PUMP_AUTO":                     (0x2F, "Automatic sequence for outputs to check the pump start / stop processes"),
        }

    def sfHwTestProtocolGetTestsSequencesList(self):
        """
        Returns a list of tests sequences

        Parameters:
        """
        return {
            ## Test sequence key -------------------- Description
            "TEST_SEQ_MINIMUM_A0_A1_SAMPLE":          ("Executes minimum checking for A0-Sample and A1-Sample devices"),
            "TEST_SEQ_MINIMUM_B0_SAMPLE":             ("Executes minimum checking for B0-Sample devices"),
        }

    def sfHwTestProtocolGetMinimumASampleTestsList(self):
        """
        Returns a list with minimum test to consider and its timeout execution for A0/A1-sample devices

        Parameters:
        """
        return [
            ## Test key ----------------------------- Stimulus ----------------------- Stim_value -- Timeout/duration
            ("HW_TEST_SUPPLY_VOLTAGES",               "",                              0x00,         500),
            ("HW_TEST_ALL_ADC_MEASUREMENTS",          "",                              0x00,         500),
            ("HW_TEST_PWM_DRIVERS_USER_MEASUREMENTS", "",                              0x00,         500),
            ("HW_TEST_MEASUREMENTS_DIAGNOSTICS",      "",                              0x00,         1000),
            ("HW_TEST_ALL_PWM_SUPPLIES",              "",                              0x00,         1500),
            ("HW_TEST_ALL_DRIVERS_STATUS",            "",                              0x00,         3500),
            ("HW_TEST_ALL_DRIVERS_SETTING",           "",                              0x00,         3500),
            ("HW_TEST_ALL_DRIVERS_FREQUENCY",         "",                              0x00,         4000),
            ("HW_TEST_ALL_DRIVERS_DUTY",              "",                              0x00,         4000),
            ("HW_TEST_UART_CHECK_LOOPBACK",           "",                              0x00,         1000),
            ("HW_TEST_CAN_ECHO",                      "SF_HW_TEST_PROTOCOL_RQST_ECHO", 0x55,         1000),
            ("HW_TEST_I2C_TEMP_HUMID_AUTO_TX",        "",                              0x00,         1000),
            ("HW_TEST_SPI_FLASH_MEM_AUTO_TX",         "",                              0x00,         1000),
            ("HW_TEST_ENC_SPI_AUTO_TX",               "",                              0x00,         500),
            ("HW_TEST_ENC_ABI_LOOPBACK",              "",                              0x00,         2500),
            ("HW_TEST_EXTRA_GPIOs_LOOPBACK",          "",                              0x00,         500),
            ("HW_TEST_LEDS",                          "",                              0x00,         500),
        ]

    def sfHwTestProtocolGetMinimumBSampleTestsList(self):
        """
        Returns a list with minimum test to consider and its timeout execution for B0-sample devices

        Parameters:
        """
        return [
            ## Test key ----------------------------- Stimulus ----------------------- Stim_value -- Timeout/duration
            ("HW_TEST_SUPPLY_VOLTAGES",               "",                              0x00,         500),
            ("HW_TEST_ALL_ADC_MEASUREMENTS",          "",                              0x00,         500),
            ("HW_TEST_PWM_DRIVERS_USER_MEASUREMENTS", "",                              0x00,         500),
            ("HW_TEST_MEASUREMENTS_DIAGNOSTICS",      "",                              0x00,         1000),
            ("HW_TEST_ALL_PWM_SUPPLIES",              "",                              0x00,         1500),
            ("HW_TEST_ALL_DRIVERS_STATUS",            "",                              0x00,         3500),
            ("HW_TEST_ALL_DRIVERS_SETTING",           "",                              0x00,         3500),
            ("HW_TEST_ALL_DRIVERS_FREQUENCY",         "",                              0x00,         4000),
            ("HW_TEST_ALL_DRIVERS_DUTY",              "",                              0x00,         4000),
            ("HW_TEST_UART_CHECK_LOOPBACK",           "",                              0x00,         1000),
            ("HW_TEST_CAN_ECHO",                      "SF_HW_TEST_PROTOCOL_RQST_ECHO", 0x55,         1000),
            ("HW_TEST_I2C_TEMP_HUMID_AUTO_TX",        "",                              0x00,         1000),
            ("HW_TEST_SPI_FLASH_MEM_AUTO_TX",         "",                              0x00,         1000),
            ("HW_TEST_ENC_SPI_AUTO_TX",               "",                              0x00,         500),
            ("HW_TEST_EXTRA_GPIOs_LOOPBACK",          "",                              0x00,         500),
            ("HW_TEST_LEDS",                          "",                              0x00,         500),
        ]

    def sfHwTestProtocolPrintMessagePayload(self, payload):
        """
        Returns a dictionary with all allowed request on the protocol

        Parameters:
            obj_instance Object received by HW Test protocol
        """
        payload_string = ""

        if len(payload) > 0:
            payload_string = (str([hex(x) for x in payload]))

        return payload_string

    def sfHwTestProtocolPrintObject(self, obj_instance):
        """
        Returns a dictionary with all allowed request on the protocol

        Parameters:
            obj_instance Object received by HW Test protocol
        """
        obj_string = ""

        if self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_KEY in obj_instance:
            if obj_instance[self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_KEY] == self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_TEST:
                test_id = int(obj_instance[self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_TEST_TYPE_KEY][0])
                obj_string = ("TEST: " +
                              str(test_id).zfill(2) +
                              ", STATE:" +
                              self._sfHwTestProtocolObjectFlagsByCommand(self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_TEST,
                                                                         int(obj_instance[self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_TEST_STATUS_KEY][0])))
            elif obj_instance[self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_KEY] == self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_ANALOG:
                analog_value = float(obj_instance[self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_VALUE_KEY])
                analog_value_str = str(f"{analog_value:.3f}")
                if analog_value >= 0.0:
                    analog_value_str = " " + analog_value_str
                obj_string = ("ANLG[" +
                              str(obj_instance[self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_ID_KEY]) +
                              "]:" +
                              analog_value_str +
                              self._sfHwTestProtocolObjectFlagsByCommand(self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_ANALOG,
                                                                         int(obj_instance[self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_FLAGS_KEY]))
                              )
            elif obj_instance[self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_KEY] == self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_BUFFER:
                buffer_array = list(obj_instance[self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_BUFFER_VALUE_KEY])
                obj_string = ("BUFFER: " + str([hex(x) for x in buffer_array]))

        return obj_string

    def sfHwTestProtocolCheckSignificantChangeInObject(self, object_before, object_after):
        is_there_a_change = False

        # # Checks if there is a significant change. For analog values, a change of at
        # # least 5% or an absolute value of the difference greater than 15 units. A
        # # change on its flags (for an analog object) is also a significant change.
        # # In other cases a single difference is considered significant
        # if object_before[self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_KEY] == self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_ANALOG:
        #     if (object_before[self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_FLAGS_KEY] !=
        #         object_after[self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_FLAGS_KEY]):
        #         is_there_a_change = True
        #     else:
        #         if abs(object_before[self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_VALUE_KEY]) > 15:
        #             value_min = object_before[self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_VALUE_KEY] * 0.95
        #             value_max = object_before[self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_VALUE_KEY] * 1.05
        #             if ((object_after[self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_VALUE_KEY] < value_min) or
        #                 (object_after[self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_VALUE_KEY] > value_max)):
        #                 is_there_a_change = True
        #         elif (abs(object_before[self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_VALUE_KEY] -
        #                 object_after[self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_VALUE_KEY]) > 15):
        #             is_there_a_change = True
        # elif object_after != object_before:
        #     is_there_a_change = True
        if object_after != object_before:
            is_there_a_change = True

        return is_there_a_change

    def sfHwTestProtocolProcessRxMessage(self, msg_len, msg_payload):
         """
         Processes a received protocol message

         Parameters:
             msg_len = Length of the message
             msg_payload = The received payload of the message
         """
         ret_action = (self.SF_HW_TEST_PROTOCOL_ACTION_DO_NOTHING, {})

         if msg_len == 8:
            message_type = msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_COMMAND_INDEX]

            # Process each type of reported message
            if message_type == self.response_dict["SF_HW_TEST_PROTOCOL_RSPN_NONE"][self.SF_HW_TEST_PROTOCOL_MSG_CODE_INDEX]:
                ret_action = self._sfHwTestProtocolProcessRxReportNone(msg_len, msg_payload)
            elif message_type == self.response_dict["SF_HW_TEST_PROTOCOL_RSPN_TEST_STATUS"][self.SF_HW_TEST_PROTOCOL_MSG_CODE_INDEX]:
                ret_action = self._sfHwTestProtocolProcessRxReportTestStatus(msg_len, msg_payload)
            elif message_type == self.response_dict["SF_HW_TEST_PROTOCOL_RSPN_ANALOG"][self.SF_HW_TEST_PROTOCOL_MSG_CODE_INDEX]:
                ret_action = self._sfHwTestProtocolProcessRxReportAnalog(msg_len, msg_payload)
            elif message_type == self.response_dict["SF_HW_TEST_PROTOCOL_RSPN_ECHO"][self.SF_HW_TEST_PROTOCOL_MSG_CODE_INDEX]:
                ret_action = self._sfHwTestProtocolProcessRxReportEcho(msg_len, msg_payload)
            elif message_type == self.response_dict["SF_HW_TEST_PROTOCOL_RSPN_BUFFER"][self.SF_HW_TEST_PROTOCOL_MSG_CODE_INDEX]:
                ret_action = self._sfHwTestProtocolProcessRxReportBuffer(msg_len, msg_payload)
         return ret_action

    def sfHwTestProtocolProcessTxMessage(self, rqst_type, instance, value, flags = 0):
        """
        Builds a protocol message

        Parameters:
            msg_len = Length of the message
            msg_payload = The received payload of the message
        """
        msg_len = 0

        # Checks if this request is in the dictionary
        if rqst_type in self.request_dict:
            msg_payload = []

            # Process each type of request message
            if rqst_type == "SF_HW_TEST_PROTOCOL_RQST_NOP":
                (msg_len, msg_payload) = self._sfHwTestProtocolProcessTxObject(rqst_type,
                                                                               self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_EMPTY,
                                                                               instance,
                                                                               0,
                                                                               flags)
            elif rqst_type == "SF_HW_TEST_PROTOCOL_RQST_SET_TEST_ENV":
                (msg_len, msg_payload) = self._sfHwTestProtocolProcessTxObject(rqst_type,
                                                                               self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_UINT32,
                                                                               instance,
                                                                               value,
                                                                               flags)
            elif rqst_type == "SF_HW_TEST_PROTOCOL_RQST_SET_TEST":
                if value in self.tests_dict:
                    (msg_len, msg_payload) = self._sfHwTestProtocolProcessTxObject(rqst_type,
                                                                                   self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_UINT32,
                                                                                   instance,
                                                                                   self.tests_dict[value][self.SF_HW_TEST_PROTOCOL_MSG_CODE_INDEX],
                                                                                   flags)
            elif rqst_type == "SF_HW_TEST_PROTOCOL_RQST_ECHO":
                (msg_len, msg_payload) = self._sfHwTestProtocolProcessTxObject(rqst_type,
                                                                               self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_BUFFER,
                                                                               instance,
                                                                               [value & 0xFF] * 4,
                                                                               flags)
            elif rqst_type == "SF_HW_TEST_PROTOCOL_RQST_SET_PWM_FREQ":
                (msg_len, msg_payload) = self._sfHwTestProtocolProcessTxObject(rqst_type,
                                                                               self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_FLOAT,
                                                                               instance,
                                                                               value,
                                                                               flags)
            elif rqst_type == "SF_HW_TEST_PROTOCOL_RQST_SET_PWM_DUTY":
                (msg_len, msg_payload) = self._sfHwTestProtocolProcessTxObject(rqst_type,
                                                                               self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_FLOAT,
                                                                               instance,
                                                                               value,
                                                                               flags)
            elif rqst_type == "SF_HW_TEST_CAN_PROTOCOL_CMD_SET_DIG_OUT":
                (msg_len, msg_payload) = self._sfHwTestProtocolProcessTxObject(rqst_type,
                                                                               self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_UINT32,
                                                                               instance,
                                                                               value,
                                                                               flags)
            elif rqst_type == "SF_HW_TEST_CAN_PROTOCOL_CMD_SET_PWM_DT":
                (msg_len, msg_payload) = self._sfHwTestProtocolProcessTxObject(rqst_type,
                                                                               self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_FLOAT,
                                                                               instance,
                                                                               value,
                                                                               flags)
            elif rqst_type == "SF_HW_TEST_CAN_PROTOCOL_CMD_SET_PWM_PULSES":
                (msg_len, msg_payload) = self._sfHwTestProtocolProcessTxObject(rqst_type,
                                                                               self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_UINT32,
                                                                               instance,
                                                                               value,
                                                                               flags)
            elif rqst_type == "SF_HW_TEST_CAN_PROTOCOL_CMD_EN_DIS_PHASE":
                (msg_len, msg_payload) = self._sfHwTestProtocolProcessTxObject(rqst_type,
                                                                               self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_UINT32,
                                                                               instance,
                                                                               value,
                                                                               flags)
            elif rqst_type == "SF_HW_TEST_PROTOCOL_RQST_SET_PUMP_DUTY":
                (msg_len, msg_payload) = self._sfHwTestProtocolProcessTxObject(rqst_type,
                                                                               self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_FLOAT,
                                                                               instance,
                                                                               value,
                                                                               flags)
            elif rqst_type == "SF_HW_TEST_PROTOCOL_RQST_SET_PUMP_FREQ":
                (msg_len, msg_payload) = self._sfHwTestProtocolProcessTxObject(rqst_type,
                                                                               self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_FLOAT,
                                                                               instance,
                                                                               value,
                                                                               flags)

            if msg_len > 0:
                ret_msg = (msg_len, msg_payload)
                return ret_msg
            else:
                return None
        else:
            return None

