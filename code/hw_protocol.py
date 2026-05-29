"""
hw_protocol.py  –  sf_hw_test_protocol for Inverter Gen3 Stage 1 HW tests.

This is a direct adaptation of STARK_FUTURE_hw_test_protocol.py (the original
interactive test tool).  All constant names, method signatures, and encode/
decode logic are preserved verbatim so that code ported from the original tool
continues to work without modification.

The class is named HwTestProtocol but aliased to sfHwTestProtocol for
compatibility with any code that uses the original class name.

CAN ID : 0x100 (shared by all requests and responses)
Frame  : always 8 bytes, standard 11-bit ID

Request codes (PC → Board): 0x00 – 0x0B
Response codes (Board → PC): 0x80 – 0x84

Status flags in a 0x81 response (FLAGS bytes, little-endian):
  0x01  BT   Board has booted
  0x02  RN   Test is running
  0x04  V    Verification attempted
  0x08  V+   Verification passed (PASS indicator)
  0x10  S    Self-test attempted
  0x20  S+   Self-test passed    (PASS indicator)
"""

import struct


class HwTestProtocol:
    """
    Encoder / decoder for the Stark Future HW Test protocol v0.1.

    Constants and method names match STARK_FUTURE_hw_test_protocol.py exactly
    so that ported code from the original tool requires no changes.
    """

    # ─── Protocol version ──────────────────────────────────────────────────
    SF_HW_TEST_PROTOCOL_VERSION = 0.1
    SF_HW_TEST_PROTOCOL_CANID   = 0x100

    # ─── Frame field indices ────────────────────────────────────────────────
    SF_HW_TEST_PROTOCOL_FRAME_COMMAND_INDEX      = 0
    SF_HW_TEST_PROTOCOL_FRAME_OBJECT_INFO_INDEX  = 1
    SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX = 2
    SF_HW_TEST_PROTOCOL_FRAME_OBJECT_FLAGS_INDEX = 6
    SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_SIZE  = 4
    SF_HW_TEST_PROTOCOL_FRAME_OBJECT_FLAGS_SIZE  = 2
    SF_HW_TEST_PROTOCOL_LEN_MSG                  = 8

    # ─── Object data types ──────────────────────────────────────────────────
    SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_EMPTY  = 0
    SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_FLOAT  = 1
    SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_UINT32 = 2
    SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_BOOL   = 3
    SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_BUFFER = 4

    # ─── Decoded object dict keys ───────────────────────────────────────────
    SF_HW_TEST_PROTOCOL_OBJECT_TYPE_KEY                 = "Type"
    SF_HW_TEST_PROTOCOL_OBJECT_FIELD_TEST_TYPE_KEY      = "Test_type"
    SF_HW_TEST_PROTOCOL_OBJECT_FIELD_TEST_STATUS_KEY    = "Test_status"
    SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_ID_KEY      = "Analog_id"
    SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_VALUE_KEY   = "Analog_value"
    SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_FLAGS_KEY   = "Analog_flags"
    SF_HW_TEST_PROTOCOL_OBJECT_FIELD_BUFFER_VALUE_KEY   = "Buffer_value"

    # ─── Object type string values ──────────────────────────────────────────
    SF_HW_TEST_PROTOCOL_OBJECT_TYPE_NONE   = "None"
    SF_HW_TEST_PROTOCOL_OBJECT_TYPE_TEST   = "test_info"
    SF_HW_TEST_PROTOCOL_OBJECT_TYPE_ANALOG = "analog_info"
    SF_HW_TEST_PROTOCOL_OBJECT_TYPE_BUFFER = "buffer_info"

    # ─── SET_TEST_ENV flags ─────────────────────────────────────────────────
    SF_HW_TEST_PROTOCOL_TEST_SET_ENV_FLAGS_CLEAR_REBOOT   = 0x01
    SF_HW_TEST_PROTOCOL_TEST_SET_ENV_FLAGS_REPORT_ENABLE  = 0x02

    # ─── SET_DIG_OUT flags ──────────────────────────────────────────────────
    SF_HW_TEST_PROTOCOL_TEST_SET_DIG_OUT_FLAGS_RESET = 0x01

    # ─── TEST_STATUS flags (in FLAGS field of 0x81 response) ────────────────
    SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_REBOOT      = 0x01
    SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_RUNNING     = 0x02
    SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_VERIF       = 0x04
    SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_VERIF_OK    = 0x08
    SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_SELFTEST    = 0x10
    SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_SELFTEST_OK = 0x20

    # ─── ANALOG flags ───────────────────────────────────────────────────────
    SF_HW_TEST_PROTOCOL_ANLG_STATUS_OBJ_FLAGS_BITMASK_OUT_OF_RANGE = 0x01
    SF_HW_TEST_PROTOCOL_ANLG_STATUS_OBJ_FLAGS_BITMASK_EXT_ID_BIT0  = 0x02
    SF_HW_TEST_PROTOCOL_ANLG_STATUS_OBJ_FLAGS_BITMASK_EXT_ID_BIT1  = 0x04

    # ─── Action codes returned by process_rx_message ────────────────────────
    SF_HW_TEST_PROTOCOL_ACTION_DO_NOTHING    = 0
    SF_HW_TEST_PROTOCOL_ACTION_HANDLE_ERROR  = 1
    SF_HW_TEST_PROTOCOL_ACTION_CLEAR_OBJECTS = 2
    SF_HW_TEST_PROTOCOL_ACTION_UPDATE_OBJECT = 3

    # ─── Processed result indices ───────────────────────────────────────────
    SF_HW_TEST_PROTOCOL_PROCESSED_ACTION_INDEX = 0
    SF_HW_TEST_PROTOCOL_PROCESSED_OBJECT_INDEX = 1

    # ─── Sequence / message dict indices ───────────────────────────────────
    SF_HW_TEST_PROTOCOL_MSG_CODE_INDEX     = 0
    SF_HW_TEST_PROTOCOL_MSG_COMMENT_INDEX  = 1

    SF_HW_TEST_PROTOCOL_SEQUENCE_ITEM_KEY_INDEX          = 0
    SF_HW_TEST_PROTOCOL_SEQUENCE_ITEM_STIMULUS_TYPE_INDEX = 1
    SF_HW_TEST_PROTOCOL_SEQUENCE_ITEM_STIMULUS_VALUE_INDEX = 2
    SF_HW_TEST_PROTOCOL_SEQUENCE_ITEM_TIMOUT_INDEX        = 3

    # ─────────────────────────────────────────────────────────────────────────
    def __init__(self):
        self.protocol_version = self.SF_HW_TEST_PROTOCOL_VERSION
        self.tests_dict    = self.sfHwTestProtocolGetTestsDictionary()
        self.request_dict  = self.sfHwTestProtocolGetRequestsDictionary()
        self.response_dict = self.sfHwTestProtocolGetResponsesDictionary()

    # ─────────────────────────────────────────────────────────────────────────
    # Private: TX object builder
    # ─────────────────────────────────────────────────────────────────────────

    def _sfHwTestProtocolProcessTxObject(self, command, obj_type, obj_instance,
                                          obj_value, obj_flags):
        msg_len = 0
        msg_payload = [0] * self.SF_HW_TEST_PROTOCOL_LEN_MSG

        if obj_type == self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_EMPTY:
            msg_len = self.SF_HW_TEST_PROTOCOL_LEN_MSG
        elif obj_type == self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_FLOAT:
            msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX:
                        self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX + 4] = \
                bytearray(struct.pack("<f", obj_value))
            msg_len = self.SF_HW_TEST_PROTOCOL_LEN_MSG
        elif obj_type == self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_UINT32:
            msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX:
                        self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX + 4] = \
                list(int(obj_value).to_bytes(4, byteorder='big'))
            msg_len = self.SF_HW_TEST_PROTOCOL_LEN_MSG
        elif obj_type == self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_BOOL:
            bool_val = 1 if obj_value else 0
            msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX:
                        self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX + 4] = \
                list(bool_val.to_bytes(4, byteorder='big'))
            msg_len = self.SF_HW_TEST_PROTOCOL_LEN_MSG
        elif obj_type == self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_BUFFER:
            msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX:
                        self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX + 4] = \
                list(obj_value[:4])
            msg_len = self.SF_HW_TEST_PROTOCOL_LEN_MSG

        if msg_len > 0:
            msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_COMMAND_INDEX] = \
                self.request_dict[command][self.SF_HW_TEST_PROTOCOL_MSG_CODE_INDEX]
            msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_INFO_INDEX] = \
                ((obj_type & 0x7) << 5) | (obj_instance & 0x1F)
            msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_FLAGS_INDEX:
                        self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_FLAGS_INDEX + 2] = \
                list(int(obj_flags).to_bytes(2, byteorder='big'))

        return [msg_len, msg_payload]

    # ─────────────────────────────────────────────────────────────────────────
    # Private: RX parsers (one per response code)
    # ─────────────────────────────────────────────────────────────────────────

    def _sfHwTestProtocolProcessRxReportNone(self, msg_len, msg_payload):
        if msg_len == 8:
            return (self.SF_HW_TEST_PROTOCOL_ACTION_CLEAR_OBJECTS, {})
        return (self.SF_HW_TEST_PROTOCOL_ACTION_HANDLE_ERROR, {})

    def _sfHwTestProtocolProcessRxReportTestStatus(self, msg_len, msg_payload):
        ret = (self.SF_HW_TEST_PROTOCOL_ACTION_HANDLE_ERROR, {})
        if msg_len >= 8:
            raw = bytes([int(x) for x in
                         msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX:
                                     self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX + 4]])
            test_value = struct.unpack("<i", raw)
            raw2 = bytes([int(x) for x in
                          msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_FLAGS_INDEX:
                                      self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_FLAGS_INDEX + 2]])
            raw2 = raw2 + bytes([0, 0])
            test_status = struct.unpack("<i", raw2)

            obj_info = {
                (self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_TEST + "0"): {
                    self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_KEY:
                        self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_TEST,
                    self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_TEST_TYPE_KEY:   test_value,
                    self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_TEST_STATUS_KEY: test_status,
                }
            }
            ret = (self.SF_HW_TEST_PROTOCOL_ACTION_UPDATE_OBJECT, obj_info)
        return ret

    def _sfHwTestProtocolProcessRxReportAnalog(self, msg_len, msg_payload):
        ret = (self.SF_HW_TEST_PROTOCOL_ACTION_HANDLE_ERROR, {})
        if msg_len >= 8:
            analog_obj_info  = msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_INFO_INDEX]
            analog_obj_type  = (analog_obj_info >> 5) & 0x07
            analog_id        = analog_obj_info & 0x1F

            raw_val = bytes([int(x) for x in
                             msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX:
                                         self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX + 4]])

            raw_flags = bytes([int(x) for x in
                               msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_FLAGS_INDEX:
                                           self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_FLAGS_INDEX + 2]])
            raw_flags = raw_flags + bytes([0, 0])
            flags_int = struct.unpack("<i", raw_flags)[0]

            # Extended channel ID bits
            if flags_int & self.SF_HW_TEST_PROTOCOL_ANLG_STATUS_OBJ_FLAGS_BITMASK_EXT_ID_BIT0:
                flags_int &= ~self.SF_HW_TEST_PROTOCOL_ANLG_STATUS_OBJ_FLAGS_BITMASK_EXT_ID_BIT0
                analog_id += 0x20
            if flags_int & self.SF_HW_TEST_PROTOCOL_ANLG_STATUS_OBJ_FLAGS_BITMASK_EXT_ID_BIT1:
                flags_int &= ~self.SF_HW_TEST_PROTOCOL_ANLG_STATUS_OBJ_FLAGS_BITMASK_EXT_ID_BIT1
                analog_id += 0x40

            analog_value = None
            if analog_obj_type == self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_FLOAT:
                analog_value = struct.unpack("<f", raw_val)[0]
            elif analog_obj_type == self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_UINT32:
                analog_value = struct.unpack("<i", raw_val)[0]

            if analog_value is not None:
                obj_info = {
                    (self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_ANALOG + str(analog_id)): {
                        self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_KEY:
                            self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_ANALOG,
                        self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_ID_KEY:    analog_id,
                        self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_VALUE_KEY: analog_value,
                        self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_FLAGS_KEY: flags_int,
                    }
                }
                ret = (self.SF_HW_TEST_PROTOCOL_ACTION_UPDATE_OBJECT, obj_info)
        return ret

    def _sfHwTestProtocolProcessRxReportEcho(self, msg_len, msg_payload):
        ret = (self.SF_HW_TEST_PROTOCOL_ACTION_HANDLE_ERROR, {})
        if msg_len >= 8:
            buf_info  = msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_INFO_INDEX]
            buf_type  = (buf_info >> 5) & 0x07
            buf_value = bytes([int(x) for x in
                               msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX:
                                           self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_VALUE_INDEX + 4]])
            if buf_type == self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_BUFFER:
                obj_info = {
                    self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_BUFFER: {
                        self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_KEY:
                            self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_BUFFER,
                        self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_BUFFER_VALUE_KEY: buf_value,
                    }
                }
                ret = (self.SF_HW_TEST_PROTOCOL_ACTION_UPDATE_OBJECT, obj_info)
        return ret

    def _sfHwTestProtocolProcessRxReportBuffer(self, msg_len, msg_payload):
        return self._sfHwTestProtocolProcessRxReportEcho(msg_len, msg_payload)

    # ─────────────────────────────────────────────────────────────────────────
    # Public: dictionaries (match original signatures exactly)
    # ─────────────────────────────────────────────────────────────────────────

    def sfHwTestProtocolGetCANid(self):
        return self.SF_HW_TEST_PROTOCOL_CANID

    def sfHwTestProtocolGetRequestsDictionary(self):
        return {
            "SF_HW_TEST_PROTOCOL_RQST_NOP":               (0x00, "Do nothing"),
            "SF_HW_TEST_PROTOCOL_RQST_SET_TEST_ENV":      (0x01, "Selects general configuration for Tests execution"),
            "SF_HW_TEST_PROTOCOL_RQST_SET_TEST":          (0x02, "Switches to the specified Test"),
            "SF_HW_TEST_PROTOCOL_RQST_ECHO":              (0x03, "Message to do an ECHO"),
            "SF_HW_TEST_PROTOCOL_RQST_SET_PWM_FREQ":      (0x04, "Set working frequency"),
            "SF_HW_TEST_PROTOCOL_RQST_SET_PWM_DUTY":      (0x05, "Set working duty cycle"),
            "SF_HW_TEST_CAN_PROTOCOL_CMD_SET_DIG_OUT":    (0x06, "Set working digital output status"),
            "SF_HW_TEST_CAN_PROTOCOL_CMD_SET_PWM_DT":     (0x07, "Set working deadtime on PWMs"),
            "SF_HW_TEST_CAN_PROTOCOL_CMD_SET_PWM_PULSES": (0x08, "Set working PWMs pulses/ticks"),
            "SF_HW_TEST_CAN_PROTOCOL_CMD_EN_DIS_PHASE":   (0x09, "Enable or disable PWM branches"),
            "SF_HW_TEST_PROTOCOL_RQST_SET_PUMP_DUTY":     (0x0A, "Set pump working duty cycle"),
            "SF_HW_TEST_PROTOCOL_RQST_SET_PUMP_FREQ":     (0x0B, "Set pump pwm frequency"),
        }

    def sfHwTestProtocolGetResponsesDictionary(self):
        return {
            "SF_HW_TEST_PROTOCOL_RSPN_NONE":          (0x80, "Reports nothing"),
            "SF_HW_TEST_PROTOCOL_RSPN_TEST_STATUS":   (0x81, "Test selected and its current status"),
            "SF_HW_TEST_PROTOCOL_RSPN_ANALOG":        (0x82, "Analog value reported"),
            "SF_HW_TEST_PROTOCOL_RSPN_ECHO":          (0x83, "Message echoed related to corresponding ECHO request"),
            "SF_HW_TEST_PROTOCOL_RSPN_BUFFER":        (0x84, "Message with a user buffer"),
        }

    def sfHwTestProtocolGetTestsDictionary(self):
        return {
            "HW_TEST_NO_TEST":                       (0x00, "Do not execute any hardware test"),
            "HW_TEST_LEDS":                          (0x01, "Test LEDs continuous"),
            "HW_TEST_SUPPLY_VOLTAGES":               (0x02, "Test that supply voltages are right"),
            "HW_TEST_ALL_ADC_MEASUREMENTS":          (0x03, "All measures connected to internal ADCs"),
            "HW_TEST_MCU_INTER_MEASUREMENTS":        (0x04, "MCU internal measurements"),
            "HW_TEST_PWM_DRIVERS_USER_MEASUREMENTS": (0x05, "All measures connected to the isolated ADC"),
            "HW_TEST_MOTOR_TEMPERATURE_LOOPBACK":    (0x06, "All MOTOR temperature measurements"),
            "HW_TEST_CAPS_TEMPERATURE_LOOPBACK":     (0x07, "All CAPACITORS temperature measurements"),
            "HW_TEST_MEASUREMENTS_DIAGNOSTICS":      (0x08, "External measurements signal integrity and/or quality"),
            "HW_TEST_PWM1_SUPPLY":                   (0x09, "PWM1 power enabling"),
            "HW_TEST_PWM2_SUPPLY":                   (0x0A, "PWM2 power enabling"),
            "HW_TEST_PWM3_SUPPLY":                   (0x0B, "PWM3 power enabling"),
            "HW_TEST_ALL_PWM_SUPPLIES":              (0x0C, "Setting all power supplies simultaneously"),
            "HW_TEST_PWM1_DRIVER_STATUS":            (0x0D, "PWM1 driver status checking"),
            "HW_TEST_PWM2_DRIVER_STATUS":            (0x0E, "PWM2 driver status checking"),
            "HW_TEST_PWM3_DRIVER_STATUS":            (0x0F, "PWM3 driver status checking"),
            "HW_TEST_ALL_DRIVERS_STATUS":            (0x10, "Setting all drivers checking status"),
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
            "HW_TEST_ALL_POWER_MODULE":              (0x1B, "Setting all power branches simultaneously"),
            "HW_TEST_DISCHARGE_AUTO_CIRCUIT":        (0x1C, "Discharge circuit continuous test"),
            "HW_TEST_CAN_AUTO_TX":                   (0x1D, "CAN continuous transmission and reception"),
            "HW_TEST_CAN_ECHO":                      (0x1E, "CAN echo (transmits what receives)"),
            "HW_TEST_UART_AUTO_TX":                  (0x1F, "UART continuous transmission and reception"),
            "HW_TEST_UART_ECHO":                     (0x20, "UART echo (transmits what receives)"),
            "HW_TEST_UART_CHECK_LOOPBACK":           (0x21, "UART transmits and checks echo received"),
            "HW_TEST_I2C_TEMP_HUMID_AUTO_TX":        (0x22, "External temperature/humidity sensor (I2C) polling"),
            "HW_TEST_SPI_FLASH_MEM_AUTO_TX":         (0x23, "External FLASH SPI representative transactions"),
            "HW_TEST_ENC_SPI_AUTO_TX":               (0x24, "Encoder SPI representative transactions"),
            "HW_TEST_ENC_SINCOS_SIN_LOOPBACK":       (0x25, "Encoder SIN differential input loopback"),
            "HW_TEST_ENC_SINCOS_COS_LOOPBACK":       (0x26, "Encoder COS differential input loopback"),
            "HW_TEST_ENC_ABI_LOOPBACK":              (0x27, "Encoder ABI automatic testing"),
            "HW_TEST_DAC_OUT_AUTO":                  (0x28, "DAC continuous output waveform"),
            "HW_TEST_EXTRA_GPIOs_LOOPBACK":          (0x29, "Test extra GPIOs loopback"),
            "HW_TEST_POWER_UNIPLR_V_LOOPBACK":       (0x2A, "Loopbacks from DACs to isolated unipolar voltage inputs"),
            "HW_TEST_POWER_BIPLR_V_LOOPBACK":        (0x2B, "Loopbacks from DACs to isolated bipolar voltage inputs"),
            "HW_TEST_DCLINK_MANAGEMENT":             (0x2C, "Manages DC-Link state"),
            "HW_TEST_POWER_MODULES_BY_PULSES":       (0x2D, "Setting all power branches for a finite number of pulses"),
            "HW_TEST_EXT_TEMPERATURE_LOOPBACK":      (0x2E, "All external input temperature measurements loopback"),
            "HW_TEST_PUMP_AUTO":                     (0x2F, "Automatic sequence for pump start/stop"),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Public: sequence lists (from original sfHwTestProtocolGetMinimum*TestsList)
    # ─────────────────────────────────────────────────────────────────────────

    def sfHwTestProtocolGetMinimumASampleTestsList(self):
        """
        Returns a list with minimum tests for A0/A1-sample devices.
        Each item: (test_key, stimulus_type, stimulus_value, timeout_ms)

        Ordering: strict ascending CAN test code.
        Groups naturally as:
          0x01..0x05  LEDs + supply / ADC / driver measurements
          0x08..0x19  diagnostics, supply enables, driver status/setting/PWM
          0x1E..0x24  comm bus tests (CAN, UART, I2C, SPI)
          0x27..0x29  loopback fixtures
        """
        return [
            ## Test key                               Stim type                          Stim val  Timeout
            ("HW_TEST_LEDS",                          "",                                0x00,     500),
            ("HW_TEST_SUPPLY_VOLTAGES",               "",                                0x00,     500),
            ("HW_TEST_ALL_ADC_MEASUREMENTS",          "",                                0x00,     500),
            ("HW_TEST_PWM_DRIVERS_USER_MEASUREMENTS", "",                                0x00,     500),
            ("HW_TEST_MEASUREMENTS_DIAGNOSTICS",      "",                                0x00,     1000),
            ("HW_TEST_ALL_PWM_SUPPLIES",              "",                                0x00,     1500),
            ("HW_TEST_ALL_DRIVERS_STATUS",            "",                                0x00,     3500),
            ("HW_TEST_ALL_DRIVERS_SETTING",           "",                                0x00,     3500),
            ("HW_TEST_ALL_DRIVERS_FREQUENCY",         "",                                0x00,     4000),
            ("HW_TEST_ALL_DRIVERS_DUTY",              "",                                0x00,     4000),
            ("HW_TEST_CAN_ECHO",                      "SF_HW_TEST_PROTOCOL_RQST_ECHO",   0x55,     1000),
            ("HW_TEST_UART_CHECK_LOOPBACK",           "",                                0x00,     1000),
            ("HW_TEST_I2C_TEMP_HUMID_AUTO_TX",        "",                                0x00,     1000),
            ("HW_TEST_SPI_FLASH_MEM_AUTO_TX",         "",                                0x00,     1000),
            ("HW_TEST_ENC_SPI_AUTO_TX",               "",                                0x00,     500),
            ("HW_TEST_ENC_ABI_LOOPBACK",              "",                                0x00,     2500),
            ("HW_TEST_EXTRA_GPIOs_LOOPBACK",          "",                                0x00,     500),
        ]

    def sfHwTestProtocolGetMinimumBSampleTestsList(self):
        """
        Returns a list with minimum tests for B-sample devices (B0/B1/B2 share
        the same sequence — they are treated as a single family).

        Differences vs the A0/A1 list:
          - HW_TEST_ENC_ABI_LOOPBACK removed  (ABI not fitted on B-sample)
          - HW_TEST_ENC_SPI_AUTO_TX  removed  (B-sample uses sin/cos encoder
                                                only; the SPI encoder path is
                                                not exercised by the bench
                                                campaign)
          - HW_TEST_MCU_INTER_MEASUREMENTS added (0x04)
          - HW_TEST_PUMP_AUTO              added (0x2F)

        Note: HW_TEST_EXT_TEMPERATURE_LOOPBACK (0x2E) is intentionally not
        in the B-sample sequence — on B0/B1 only EXT_TEMP1 and EXT_TEMP2 are
        populated, so the firmware's DAC sweep across all four NTC paths
        always reports two unconnected channels as out-of-range. The test
        remains available via SET_TEST for diagnostic use on boards with
        all four NTCs fitted.

        Result is kept in strict ascending CAN test code order, same as the
        A-list (see sfHwTestProtocolGetMinimumASampleTestsList).
        """
        _b_excluded = {"HW_TEST_ENC_ABI_LOOPBACK", "HW_TEST_ENC_SPI_AUTO_TX"}
        base = [item for item in self.sfHwTestProtocolGetMinimumASampleTestsList()
                if item[0] not in _b_excluded]

        b_additions = [
            ## Test key                               Stim type   Stim val  Timeout
            ("HW_TEST_MCU_INTER_MEASUREMENTS",        "",         0x00,     500),    # 0x04
            ("HW_TEST_ENC_SINCOS_SIN_LOOPBACK",       "",         0x00,     1500),   # 0x25  sin front-end
            ("HW_TEST_ENC_SINCOS_COS_LOOPBACK",       "",         0x00,     1500),   # 0x26  cos front-end
            ("HW_TEST_POWER_UNIPLR_V_LOOPBACK",       "",         0x00,     2000),   # 0x2A  DC-link voltage conditioning
            ("HW_TEST_POWER_BIPLR_V_LOOPBACK",        "",         0x00,     2000),   # 0x2B  UV/WV phase-to-DCneg conditioning
            ("HW_TEST_PUMP_AUTO",                     "",         0x00,     5000),   # 0x2F
        ]

        merged = base + b_additions
        # Sort by the test code looked up in the protocol's test dictionary
        tests_dict = self.sfHwTestProtocolGetTestsDictionary()
        merged.sort(key=lambda item: tests_dict[item[0]][0])
        return merged

    # ─── 3-phase sub-sequences (B-sample) ────────────────────────────────────
    #
    # The full B-sample sequence is split into three phases by *how* they need
    # to be run:
    #
    #   Phase 1 — Self auto-verification  : no operator input required (the
    #             test-fixture jumpers for UART/GPIO loopback stay in place).
    #             Suitable for unattended Bash execution.
    #
    #   Phase 2 — Power modules (external) : HW_TEST_ALL_POWER_MODULE (0x1B),
    #             driven by the scope-assisted run_power_module_sweep.py /
    #             pm_step_session.py — operator moves the probe per switch.
    #             NOT in either sequence list here; orchestrated separately.
    #
    #   Phase 3 — Operator-verified tests: each needs the operator to do
    #             something physical before or during the test runs. On
    #             B-sample this includes the LED visual check (HW_TEST_LEDS,
    #             operator confirms LED1/LED2 blink) and four DAC-injection
    #             loopbacks (operator wires a DAC output to an analog input):
    #             ENC_SINCOS_SIN/COS, POWER_UNIPLR_V, POWER_BIPLR_V.
    #
    # Phase 1 + Phase 3 ≡ the full B-sample list (sfHwTestProtocolGetMinimum
    # BSampleTestsList). Each is sorted by ascending CAN test code.

    BSAMPLE_OPERATOR_VERIFIED_KEYS = (
        "HW_TEST_LEDS",                      # 0x01 — visual LED check
        "HW_TEST_ENC_SINCOS_SIN_LOOPBACK",   # 0x25 — DAC injection
        "HW_TEST_ENC_SINCOS_COS_LOOPBACK",   # 0x26 — DAC injection
        "HW_TEST_POWER_UNIPLR_V_LOOPBACK",   # 0x2A — DAC injection
        "HW_TEST_POWER_BIPLR_V_LOOPBACK",    # 0x2B — DAC injection
    )
    # Backward-compat alias (the prior name was DAC-only; LEDs are now also
    # in this set — kept for any external code that imports the old name).
    BSAMPLE_LOOPBACK_DAC_KEYS = BSAMPLE_OPERATOR_VERIFIED_KEYS

    def sfHwTestProtocolGetBSampleSelfTestsList(self):
        """Phase 1 — self auto-verification tests for B-sample (no operator
        input). Excludes the operator-verified tests listed in
        BSAMPLE_OPERATOR_VERIFIED_KEYS (which live in Phase 3)."""
        op = set(self.BSAMPLE_OPERATOR_VERIFIED_KEYS)
        return [item for item in self.sfHwTestProtocolGetMinimumBSampleTestsList()
                if item[0] not in op]

    def sfHwTestProtocolGetBSampleOperatorVerifiedTestsList(self):
        """Phase 3 — operator-verified tests for B-sample (LED visual check
        and DAC-injection loopbacks). Sorted by ascending CAN test code."""
        op = set(self.BSAMPLE_OPERATOR_VERIFIED_KEYS)
        return [item for item in self.sfHwTestProtocolGetMinimumBSampleTestsList()
                if item[0] in op]

    # Backward-compat alias (older callers / docs referred to "Loopback").
    def sfHwTestProtocolGetBSampleLoopbackTestsList(self):
        return self.sfHwTestProtocolGetBSampleOperatorVerifiedTestsList()

    # ─────────────────────────────────────────────────────────────────────────
    # Public: main TX / RX processing (match original method signatures)
    # ─────────────────────────────────────────────────────────────────────────

    def sfHwTestProtocolProcessTxMessage(self, rqst_type, instance, value, flags=0):
        """
        Build a protocol TX frame.  Returns [msg_len, msg_payload] list.
        rqst_type must be a key in sfHwTestProtocolGetRequestsDictionary().

        Special case: SET_TEST accepts either a test_key string (e.g.
        "HW_TEST_CAN_ECHO") or an integer test code directly.
        """
        if rqst_type not in self.request_dict:
            return [0, []]

        if rqst_type == "SF_HW_TEST_PROTOCOL_RQST_NOP":
            return self._sfHwTestProtocolProcessTxObject(
                rqst_type, self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_EMPTY,
                instance, 0, flags)

        elif rqst_type == "SF_HW_TEST_PROTOCOL_RQST_SET_TEST_ENV":
            return self._sfHwTestProtocolProcessTxObject(
                rqst_type, self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_UINT32,
                instance, value, flags)

        elif rqst_type == "SF_HW_TEST_PROTOCOL_RQST_SET_TEST":
            # value may be a test_key string or a numeric code
            if isinstance(value, str) and value in self.tests_dict:
                code = self.tests_dict[value][self.SF_HW_TEST_PROTOCOL_MSG_CODE_INDEX]
            else:
                code = int(value)
            return self._sfHwTestProtocolProcessTxObject(
                rqst_type, self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_UINT32,
                instance, code, flags)

        elif rqst_type == "SF_HW_TEST_PROTOCOL_RQST_ECHO":
            # value = single byte to fill the 4-byte payload
            pattern = [value & 0xFF] * 4
            return self._sfHwTestProtocolProcessTxObject(
                rqst_type, self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_BUFFER,
                instance, pattern, flags)

        elif rqst_type in ("SF_HW_TEST_CAN_PROTOCOL_CMD_SET_DIG_OUT",
                           "SF_HW_TEST_CAN_PROTOCOL_CMD_SET_PWM_PULSES",
                           "SF_HW_TEST_CAN_PROTOCOL_CMD_EN_DIS_PHASE"):
            # These are UINT32 in the firmware / original tool (NOT float):
            #   SET_DIG_OUT    – digital output state/pulse-ms
            #   SET_PWM_PULSES – number of PWM ticks
            #   EN_DIS_PHASE   – 0/1 enable per phase (object index selects U/V/W
            #                    or all phases at index 0)
            return self._sfHwTestProtocolProcessTxObject(
                rqst_type, self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_UINT32,
                instance, int(value), flags)

        else:
            # Generic: float (SET_PWM_FREQ / SET_PWM_DUTY / SET_PWM_DT /
            # SET_PUMP_DUTY / SET_PUMP_FREQ) — matches the original tool.
            return self._sfHwTestProtocolProcessTxObject(
                rqst_type, self.SF_HW_TEST_PROTOCOL_FRAME_OBJECT_TYPE_FLOAT,
                instance, float(value), flags)

    def sfHwTestProtocolProcessRxMessage(self, msg_len, msg_payload):
        """
        Decode a received CAN frame.
        Returns (action_code, object_dict).

        Mirrors the original sfHwTestProtocolProcessRxMessage() exactly.
        """
        ret = (self.SF_HW_TEST_PROTOCOL_ACTION_DO_NOTHING, {})

        if msg_len != 8:
            return ret

        msg_type = msg_payload[self.SF_HW_TEST_PROTOCOL_FRAME_COMMAND_INDEX]

        if msg_type == self.response_dict["SF_HW_TEST_PROTOCOL_RSPN_NONE"][0]:
            ret = self._sfHwTestProtocolProcessRxReportNone(msg_len, msg_payload)
        elif msg_type == self.response_dict["SF_HW_TEST_PROTOCOL_RSPN_TEST_STATUS"][0]:
            ret = self._sfHwTestProtocolProcessRxReportTestStatus(msg_len, msg_payload)
        elif msg_type == self.response_dict["SF_HW_TEST_PROTOCOL_RSPN_ANALOG"][0]:
            ret = self._sfHwTestProtocolProcessRxReportAnalog(msg_len, msg_payload)
        elif msg_type == self.response_dict["SF_HW_TEST_PROTOCOL_RSPN_ECHO"][0]:
            ret = self._sfHwTestProtocolProcessRxReportEcho(msg_len, msg_payload)
        elif msg_type == self.response_dict["SF_HW_TEST_PROTOCOL_RSPN_BUFFER"][0]:
            ret = self._sfHwTestProtocolProcessRxReportBuffer(msg_len, msg_payload)

        return ret

    def sfHwTestProtocolPrintObject(self, obj_instance):
        """Return a human-readable string for a decoded object (for logging)."""
        obj_string = ""
        type_key   = self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_KEY

        if type_key not in obj_instance:
            return obj_string

        obj_type = obj_instance[type_key]

        if obj_type == self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_TEST:
            test_id  = int(obj_instance[self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_TEST_TYPE_KEY][0])
            flags    = int(obj_instance[self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_TEST_STATUS_KEY][0])
            flag_str = self._flags_to_string(flags)
            obj_string = f"TEST: {test_id:02d}, STATE:{flag_str}"

        elif obj_type == self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_ANALOG:
            val = float(obj_instance[self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_VALUE_KEY])
            ch  = obj_instance[self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_ANALOG_ID_KEY]
            obj_string = f"ANLG[{ch}]:{val:+.3f}"

        elif obj_type == self.SF_HW_TEST_PROTOCOL_OBJECT_TYPE_BUFFER:
            buf = list(obj_instance[self.SF_HW_TEST_PROTOCOL_OBJECT_FIELD_BUFFER_VALUE_KEY])
            obj_string = f"BUFFER: {[hex(b) for b in buf]}"

        return obj_string

    # ─────────────────────────────────────────────────────────────────────────
    # Private: flag formatting helper
    # ─────────────────────────────────────────────────────────────────────────

    def _flags_to_string(self, flags: int) -> str:
        parts = []
        if flags & self.SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_REBOOT:
            parts.append("BT")
        if flags & self.SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_RUNNING:
            parts.append("RN")
        if flags & self.SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_VERIF:
            if flags & self.SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_VERIF_OK:
                parts.append("V+")
            else:
                parts.append("V-")
        if flags & self.SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_SELFTEST:
            if flags & self.SF_HW_TEST_PROTOCOL_TEST_STATUS_OBJ_FLAGS_BITMASK_SELFTEST_OK:
                parts.append("S+")
            else:
                parts.append("S-")
        return " ".join(parts) if parts else "—"


# ── Alias for code that uses the original class name ──────────────────────
sfHwTestProtocol = HwTestProtocol
