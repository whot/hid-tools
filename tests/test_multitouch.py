#!/bin/env python3
# -*- coding: utf-8 -*-
#
# Hid tools / tests/multitouch.py: unittest for multitouch devices
#
# Copyright (c) 2017 Benjamin Tissoires <benjamin.tissoires@gmail.com>
# Copyright (c) 2017 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import base
import hid
import libevdev
import sys
import time
import unittest
from base import main, setUpModule, tearDownModule  # noqa


def BIT(x):
    return 1 << x


mt_quirks = {
    'NOT_SEEN_MEANS_UP':            BIT(0),
    'SLOT_IS_CONTACTID':            BIT(1),
    'CYPRESS':                      BIT(2),
    'SLOT_IS_CONTACTNUMBER':        BIT(3),
    'ALWAYS_VALID':                 BIT(4),
    'VALID_IS_INRANGE':             BIT(5),
    'VALID_IS_CONFIDENCE':          BIT(6),
    'CONFIDENCE':                   BIT(7),
    'SLOT_IS_CONTACTID_MINUS_ONE':  BIT(8),
    'NO_AREA':                      BIT(9),
    'IGNORE_DUPLICATES':            BIT(10),
    'HOVERING':                     BIT(11),
    'CONTACT_CNT_ACCURATE':         BIT(12),
    'FORCE_GET_FEATURE':            BIT(13),
    'FIX_CONST_CONTACT_ID':         BIT(14),
    'TOUCH_SIZE_SCALING':           BIT(15),
    'STICKY_FINGERS':               BIT(16),
    'ASUS_CUSTOM_UP':               BIT(17),
    'WIN8_PTP_BUTTONS':             BIT(18),
}


class Data(object):
    pass


class Touch(object):
    def __init__(self, id, x, y):
        self.contactid = id
        self.x = x
        self.y = y
        self.cx = x
        self.cy = y
        self.tipswitch = True
        self.confidence = True
        self.pressure = 100
        self.azimuth = 0
        self.inrange = True
        self.width = 10
        self.height = 10


class Pen(Touch):
    def __init__(self, x, y):
        super(Pen, self).__init__(0, x, y)
        self.barrel = False
        self.invert = False
        self.eraser = False
        self.x_tilt = False
        self.y_tilt = False
        self.twist = 0


class Digitizer(base.UHIDTest):
    @classmethod
    def msCertificationBlob(cls, reportID):
        return f'''
        Usage Page (Digitizers)
        Usage (Touch Screen)
        Collection (Application)
         Report ID ({reportID})
         Usage Page (0xff00)
         Usage (0xc5)
         Logical Minimum (0)
         Logical Maximum (255)
         Report Size (8)
         Report Count (256)
         Feature (Data,Var,Abs)
        End Collection
    '''

    def __init__(self, name, rdesc_str=None, rdesc=None, application='Touch Screen', max_contacts=None, info=(3, 1, 2), quirks=None):
        super(Digitizer, self).__init__(name, rdesc_str, rdesc)
        self.info = info
        self.scantime = 0
        self.quirks = quirks
        if max_contacts is None:
            self.max_contacts = 1
            for features in self.parsed_rdesc.feature_reports.values():
                for feature in features:
                    if feature.usage_name == 'Contact Max':
                        self.max_contacts = feature.logical_max
        else:
            self.max_contacts = max_contacts
        self.application = application
        self.cur_application = application

        for features in self.parsed_rdesc.feature_reports.values():
                for feature in features:
                    if feature.usage_name == 'Inputmode':
                        self.cur_application = 'Mouse'

        self.fields = []
        for r in self.parsed_rdesc.input_reports.values():
            if r.application_name == self.application:
                self.fields = [f.usage_name for f in r]

        # self.parsed_rdesc.dump(sys.stdout)
        self.create_kernel_device()

    @property
    def touches_in_a_report(self):
        return self.fields.count('Contact Id')

    def event(self, slots, global_data=None, contact_count=None, incr_scantime=True):
        if incr_scantime:
            self.scantime += 1
        rs = []
        # make sure we have only the required number of available slots
        slots = slots[:self.max_contacts]

        if global_data is None:
            global_data = Data()
        if contact_count is None:
            global_data.contactcount = len(slots)
        else:
            global_data.contactcount = contact_count
        global_data.scantime = self.scantime

        while len(slots):
            r = self.format_report(application=self.cur_application, data=slots, global_data=global_data)
            self.call_input_event(r)
            rs.append(r)
            self.contactcount = 0
        return rs

    @property
    def evdev(self):
        if self.application not in self.input_nodes:
            return None

        return self.input_nodes[self.application]

    def get_report(self, req, rnum, rtype):
        if rtype != self.UHID_FEATURE_REPORT:
            self.call_get_report(req, [], 1)
            return

        rdesc = None
        for v in self.parsed_rdesc.feature_reports.values():
            if v.report_ID == rnum:
                rdesc = v

        if rdesc is None:
            self.call_get_report(req, [], 1)
            return

        if 'Contact Max' not in [f.usage_name for f in rdesc]:
            self.call_get_report(req, [], 1)
            return

        self.contactmax = self.max_contacts
        r = rdesc.format_report([self], None)
        self.call_get_report(req, r, 0)

    def set_report(self, req, rnum, rtype, size, data):
        if rtype != self.UHID_FEATURE_REPORT:
            self.call_set_report(req, 1)

        rdesc = None
        for v in self.parsed_rdesc.feature_reports.values():
            if v.report_ID == rnum:
                rdesc = v

        if rdesc is None:
            self.call_set_report(req, 1)
            return

        if 'Inputmode' not in [f.usage_name for f in rdesc]:
            self.call_set_report(req, 0)
            return

        Inputmode_seen = False
        for f in rdesc:
            if 'Inputmode' == f.usage_name and not Inputmode_seen:
                Inputmode_seen = True
                values = f.get_values(data)
                assert len(values) == 1
                value = values[0]

                if value == 0:
                    self.cur_application = 'Mouse'
                elif value == 2:
                    self.cur_application = 'Touch Screen'
                elif value == 3:
                    self.cur_application = 'Touch Pad'

        self.call_set_report(req, 0)


class PTP(Digitizer):
    def __init__(self, name, type='Click Pad', rdesc_str=None, rdesc=None, application='Touch Pad', max_contacts=None):
        self.type = type.lower().replace(' ', '')
        if self.type == 'clickpad':
            self.buttontype = 0
        else:  # pressurepad
            self.buttontype = 1
        self.clickpad_state = False
        self.left_state = False
        self.right_state = False
        super(PTP, self).__init__(name, rdesc_str, rdesc, application, max_contacts)

    def event(self, slots=None, click=None, left=None, right=None, contact_count=None, incr_scantime=True):
        # update our internal state
        if click is not None:
            self.clickpad_state = click
        if left is not None:
            self.left_state = left
        if right is not None:
            self.right_state = right

        # now create the global data
        global_data = Data()
        global_data.b1 = 1 if self.clickpad_state else 0
        global_data.b2 = 1 if self.left_state else 0
        global_data.b3 = 1 if self.right_state else 0

        if slots is None:
            slots = [Data()]

        return super(PTP, self).event(slots, global_data, contact_count, incr_scantime)


class MinWin8TSParallel(Digitizer):
    def __init__(self, max_slots):
        self.max_slots = max_slots
        self.phys_max = 120, 90
        rdesc_finger_str = f'''
            Usage Page (Digitizers)
            Usage (Finger)
            Collection (Logical)
             Report Size (1)
             Report Count (1)
             Logical Minimum (0)
             Logical Maximum (1)
             Usage (Tip Switch)
             Input (Data,Var,Abs)
             Report Size (7)
             Logical Maximum (127)
             Input (Cnst,Var,Abs)
             Report Size (8)
             Logical Maximum (255)
             Usage (Contact Id)
             Input (Data,Var,Abs)
             Report Size (16)
             Unit Exponent (-1)
             Unit (Centimeter,SILinear)
             Logical Maximum (4095)
             Physical Minimum (0)
             Physical Maximum ({self.phys_max[0]})
             Usage Page (Generic Desktop)
             Usage (X)
             Input (Data,Var,Abs)
             Physical Maximum ({self.phys_max[1]})
             Usage (Y)
             Input (Data,Var,Abs)
             Usage Page (Digitizers)
             Usage (Azimuth)
             Logical Maximum (360)
             Unit (Degrees,SILinear)
             Report Size (16)
             Input (Data,Var,Abs)
            End Collection
'''
        rdesc_str = f'''
           Usage Page (Digitizers)
           Usage (Touch Screen)
           Collection (Application)
            Report ID (1)
            {rdesc_finger_str * self.max_slots}
            Unit Exponent (-4)
            Unit (Seconds,SILinear)
            Logical Maximum (65535)
            Physical Maximum (65535)
            Usage Page (Digitizers)
            Usage (Scan Time)
            Input (Data,Var,Abs)
            Report Size (8)
            Logical Maximum (255)
            Usage (Contact Count)
            Input (Data,Var,Abs)
            Report ID (2)
            Logical Maximum ({self.max_slots})
            Usage (Contact Max)
            Feature (Data,Var,Abs)
          End Collection
          {Digitizer.msCertificationBlob(68)}
'''
        super(MinWin8TSParallel, self).__init__(f'uhid test parallel {self.max_slots}',
                                                rdesc_str)


class MinWin8TSHybrid(Digitizer):
    def __init__(self):
        self.max_slots = 10
        self.phys_max = 120, 90
        rdesc_finger_str = f'''
            Usage Page (Digitizers)
            Usage (Finger)
            Collection (Logical)
             Report Size (1)
             Report Count (1)
             Logical Minimum (0)
             Logical Maximum (1)
             Usage (Tip Switch)
             Input (Data,Var,Abs)
             Report Size (7)
             Logical Maximum (127)
             Input (Cnst,Var,Abs)
             Report Size (8)
             Logical Maximum (255)
             Usage (Contact Id)
             Input (Data,Var,Abs)
             Report Size (16)
             Unit Exponent (-1)
             Unit (Centimeter,SILinear)
             Logical Maximum (4095)
             Physical Minimum (0)
             Physical Maximum ({self.phys_max[0]})
             Usage Page (Generic Desktop)
             Usage (X)
             Input (Data,Var,Abs)
             Physical Maximum ({self.phys_max[1]})
             Usage (Y)
             Input (Data,Var,Abs)
            End Collection
'''
        rdesc_str = f'''
           Usage Page (Digitizers)
           Usage (Touch Screen)
           Collection (Application)
            Report ID (1)
            {rdesc_finger_str * 2}
            Unit Exponent (-4)
            Unit (Seconds,SILinear)
            Logical Maximum (65535)
            Physical Maximum (65535)
            Usage Page (Digitizers)
            Usage (Scan Time)
            Input (Data,Var,Abs)
            Report Size (8)
            Logical Maximum (255)
            Usage (Contact Count)
            Input (Data,Var,Abs)
            Report ID (2)
            Logical Maximum ({self.max_slots})
            Usage (Contact Max)
            Feature (Data,Var,Abs)
          End Collection
          {Digitizer.msCertificationBlob(68)}
'''
        super(MinWin8TSHybrid, self).__init__('uhid test hybrid',
                                              rdesc_str)


class BaseTest:
    class TestMultitouch(base.BaseTestCase.TestUhid):
        def __init__(self, methodName='runTest'):
            super(BaseTest.TestMultitouch, self).__init__(methodName)
            self.__create_device = self._create_device
            self.__assertName = self.assertName

        def _create_device(self):
            raise Exception('please reimplement me in subclasses')

        def assertName(self, uhdev):
            self.assertEqual(uhdev.evdev.name, uhdev.name)

        def get_slot(self, uhdev, t, default):
            if uhdev.quirks is None:
                return default

            if 'SLOT_IS_CONTACTID' in uhdev.quirks:
                    return t.contactid

            return default

        def test_mt_creation(self):
            """Make sure the device gets processed by the kernel and creates
            the expected application input node.

            If this fail, there is something wrong in the device report
            descriptors."""
            with self.__create_device() as uhdev:
                while uhdev.application not in uhdev.input_nodes:
                    uhdev.process_one_event(10)

                # some sanity checking for the quirks
                if uhdev.quirks is not None:
                    for q in uhdev.quirks:
                        self.assertIn(q, mt_quirks)

                self.assertIsNotNone(uhdev.evdev)
                self.__assertName(uhdev)
                self.assertEqual(uhdev.evdev.num_slots, uhdev.max_contacts)
                self.assertEqual(len(uhdev.next_sync_events()), 0)

                uhdev.destroy()
                while uhdev.opened:
                    if uhdev.process_one_event(100) == 0:
                        break
                with self.assertRaises(OSError):
                    uhdev.evdev.fd.read()

        def test_required_usages(self):
            """Make sure the device exports the correct required features and
            inputs."""
            with self.__create_device() as uhdev:
                rdesc = uhdev.parsed_rdesc
                for feature in rdesc.feature_reports.values():
                    for field in feature:
                        if field.usage in hid.inv_usages and hid.inv_usages[field.usage] == 'Contact Max':
                            self.assertIn(hid.inv_usages[field.application], ['Touch Screen', 'Touch Pad', 'System Multi-Axis Controller'])
                        if field.usage in hid.inv_usages and hid.inv_usages[field.usage] == 'Button Type':
                            self.assertIn(hid.inv_usages[field.application], ['Touch Pad'])
                        if field.usage in hid.inv_usages and hid.inv_usages[field.usage] == 'Inputmode':
                            self.assertIn(hid.inv_usages[field.application], ['Touch Pad', 'Device Configuration'])

                uhdev.destroy()

        def test_mt_single_touch(self):
            """send a single touch in the first slot of the device,
            and release it."""
            with self.__create_device() as uhdev:
                while uhdev.application not in uhdev.input_nodes:
                    uhdev.process_one_event(10)

                t0 = Touch(1, 50, 100)
                r = uhdev.event([t0])
                events = uhdev.next_sync_events()
                self.debug_reports(r, uhdev); print(events)

                slot = self.get_slot(uhdev, t0, 0)

                self.assertIn(libevdev.InputEvent(libevdev.EV_KEY.BTN_TOUCH, 1), events)
                self.assertEqual(uhdev.evdev.slot_value(slot, libevdev.EV_ABS.ABS_MT_TRACKING_ID), 0)
                self.assertEqual(uhdev.evdev.slot_value(slot, libevdev.EV_ABS.ABS_MT_POSITION_X), 50)
                self.assertEqual(uhdev.evdev.slot_value(slot, libevdev.EV_ABS.ABS_MT_POSITION_Y), 100)

                t0.tipswitch = False
                t0.inrange = False
                r = uhdev.event([t0])
                events = uhdev.next_sync_events()
                self.debug_reports(r, uhdev); print(events)
                self.assertIn(libevdev.InputEvent(libevdev.EV_KEY.BTN_TOUCH, 0), events)
                self.assertEqual(uhdev.evdev.slot_value(slot, libevdev.EV_ABS.ABS_MT_TRACKING_ID), -1)

                uhdev.destroy()

        def test_mt_dual_touch(self):
            """Send 2 touches in the first 2 slots.
            Make sure the kernel sees this as a dual touch.
            Release and check

            Note: PTP will send here BTN_DOUBLETAP emulation"""
            with self.__create_device() as uhdev:
                while uhdev.application not in uhdev.input_nodes:
                    uhdev.process_one_event(10)

                t0 = Touch(1, 50, 100)
                t1 = Touch(2, 150, 200)
                r = uhdev.event([t0])
                events = uhdev.next_sync_events()
                self.debug_reports(r, uhdev); print(events)

                slot0 = self.get_slot(uhdev, t0, 0)
                slot1 = self.get_slot(uhdev, t1, 1)

                self.assertIn(libevdev.InputEvent(libevdev.EV_KEY.BTN_TOUCH, 1), events)
                self.assertEqual(uhdev.evdev.value[libevdev.EV_KEY.BTN_TOUCH], 1)
                self.assertEqual(uhdev.evdev.slot_value(slot0, libevdev.EV_ABS.ABS_MT_TRACKING_ID), 0)
                self.assertEqual(uhdev.evdev.slot_value(slot0, libevdev.EV_ABS.ABS_MT_POSITION_X), 50)
                self.assertEqual(uhdev.evdev.slot_value(slot0, libevdev.EV_ABS.ABS_MT_POSITION_Y), 100)
                self.assertEqual(uhdev.evdev.slot_value(slot1, libevdev.EV_ABS.ABS_MT_TRACKING_ID), -1)

                r = uhdev.event([t0, t1])
                events = uhdev.next_sync_events()
                self.debug_reports(r, uhdev); print(events)
                self.assertNotIn(libevdev.InputEvent(libevdev.EV_KEY.BTN_TOUCH), events)
                self.assertEqual(uhdev.evdev.value[libevdev.EV_KEY.BTN_TOUCH], 1)
                self.assertNotIn(libevdev.InputEvent(libevdev.EV_ABS.ABS_MT_POSITION_X, 5), events)
                self.assertNotIn(libevdev.InputEvent(libevdev.EV_ABS.ABS_MT_POSITION_Y, 10), events)
                self.assertEqual(uhdev.evdev.slot_value(slot0, libevdev.EV_ABS.ABS_MT_TRACKING_ID), 0)
                self.assertEqual(uhdev.evdev.slot_value(slot0, libevdev.EV_ABS.ABS_MT_POSITION_X), 50)
                self.assertEqual(uhdev.evdev.slot_value(slot0, libevdev.EV_ABS.ABS_MT_POSITION_Y), 100)
                self.assertEqual(uhdev.evdev.slot_value(slot1, libevdev.EV_ABS.ABS_MT_TRACKING_ID), 1)
                self.assertEqual(uhdev.evdev.slot_value(slot1, libevdev.EV_ABS.ABS_MT_POSITION_X), 150)
                self.assertEqual(uhdev.evdev.slot_value(slot1, libevdev.EV_ABS.ABS_MT_POSITION_Y), 200)

                t0.tipswitch = False
                t0.inrange = False
                r = uhdev.event([t0, t1])
                events = uhdev.next_sync_events()
                self.debug_reports(r, uhdev); print(events)
                self.assertEqual(uhdev.evdev.slot_value(slot0, libevdev.EV_ABS.ABS_MT_TRACKING_ID), -1)
                self.assertEqual(uhdev.evdev.slot_value(slot1, libevdev.EV_ABS.ABS_MT_TRACKING_ID), 1)
                self.assertNotIn(libevdev.InputEvent(libevdev.EV_ABS.ABS_MT_POSITION_X), events)
                self.assertNotIn(libevdev.InputEvent(libevdev.EV_ABS.ABS_MT_POSITION_Y), events)

                t1.tipswitch = False
                t1.inrange = False
                r = uhdev.event([t1])
                events = uhdev.next_sync_events()
                self.debug_reports(r, uhdev); print(events)
                self.assertEqual(uhdev.evdev.slot_value(slot0, libevdev.EV_ABS.ABS_MT_TRACKING_ID), -1)
                self.assertEqual(uhdev.evdev.slot_value(slot1, libevdev.EV_ABS.ABS_MT_TRACKING_ID), -1)

                uhdev.destroy()

        def test_mt_triple_tap(self):
            """Send 3 touches in the first 3 slots.
            Make sure the kernel sees this as a triple touch.
            Release and check

            Note: PTP will send here BTN_TRIPLETAP emulation"""
            with self.__create_device() as uhdev:
                if uhdev.max_contacts <= 2:
                    uhdev.destroy()
                    raise unittest.SkipTest('Device not compatible')
                while uhdev.application not in uhdev.input_nodes:
                    uhdev.process_one_event(10)

                t0 = Touch(1, 50, 100)
                t1 = Touch(2, 150, 200)
                t2 = Touch(3, 250, 300)
                r = uhdev.event([t0, t1, t2])
                events = uhdev.next_sync_events()
                self.debug_reports(r, uhdev); print(events)

                slot0 = self.get_slot(uhdev, t0, 0)
                slot1 = self.get_slot(uhdev, t1, 1)
                slot2 = self.get_slot(uhdev, t2, 2)

                self.assertEqual(uhdev.evdev.slot_value(slot0, libevdev.EV_ABS.ABS_MT_TRACKING_ID), 0)
                self.assertEqual(uhdev.evdev.slot_value(slot0, libevdev.EV_ABS.ABS_MT_POSITION_X), 50)
                self.assertEqual(uhdev.evdev.slot_value(slot0, libevdev.EV_ABS.ABS_MT_POSITION_Y), 100)
                self.assertEqual(uhdev.evdev.slot_value(slot1, libevdev.EV_ABS.ABS_MT_TRACKING_ID), 1)
                self.assertEqual(uhdev.evdev.slot_value(slot1, libevdev.EV_ABS.ABS_MT_POSITION_X), 150)
                self.assertEqual(uhdev.evdev.slot_value(slot1, libevdev.EV_ABS.ABS_MT_POSITION_Y), 200)
                self.assertEqual(uhdev.evdev.slot_value(slot2, libevdev.EV_ABS.ABS_MT_TRACKING_ID), 2)
                self.assertEqual(uhdev.evdev.slot_value(slot2, libevdev.EV_ABS.ABS_MT_POSITION_X), 250)
                self.assertEqual(uhdev.evdev.slot_value(slot2, libevdev.EV_ABS.ABS_MT_POSITION_Y), 300)

                t0.tipswitch = False
                t0.inrange = False
                t1.tipswitch = False
                t1.inrange = False
                t2.tipswitch = False
                t2.inrange = False
                r = uhdev.event([t0, t1, t2])
                events = uhdev.next_sync_events()
                self.debug_reports(r, uhdev); print(events)

                self.assertEqual(uhdev.evdev.slot_value(slot0, libevdev.EV_ABS.ABS_MT_TRACKING_ID), -1)
                self.assertEqual(uhdev.evdev.slot_value(slot1, libevdev.EV_ABS.ABS_MT_TRACKING_ID), -1)
                self.assertEqual(uhdev.evdev.slot_value(slot2, libevdev.EV_ABS.ABS_MT_TRACKING_ID), -1)

                uhdev.destroy()

        def test_mt_max_contact(self):
            """send the maximum number of contact as reported by the device.
            Make sure all contacts are forwarded and that there is no miss.
            Release and check."""
            with self.__create_device() as uhdev:
                while uhdev.application not in uhdev.input_nodes:
                    uhdev.process_one_event(10)

                touches = [Touch(i, (i + 3) * 20, (i + 3) * 20 + 5) for i in range(uhdev.max_contacts)]
                r = uhdev.event(touches)
                events = uhdev.next_sync_events()
                self.debug_reports(r, uhdev); print(events)
                for i, t in enumerate(touches):
                    slot = self.get_slot(uhdev, t, i)

                    self.assertEqual(uhdev.evdev.slot_value(slot, libevdev.EV_ABS.ABS_MT_TRACKING_ID), i)
                    self.assertEqual(uhdev.evdev.slot_value(slot, libevdev.EV_ABS.ABS_MT_POSITION_X), t.x)
                    self.assertEqual(uhdev.evdev.slot_value(slot, libevdev.EV_ABS.ABS_MT_POSITION_Y), t.y)

                for t in touches:
                    t.tipswitch = False
                    t.inrange = False

                r = uhdev.event(touches)
                events = uhdev.next_sync_events()
                self.debug_reports(r, uhdev); print(events)
                for i, t in enumerate(touches):
                    slot = self.get_slot(uhdev, t, i)

                    self.assertEqual(uhdev.evdev.slot_value(slot, libevdev.EV_ABS.ABS_MT_TRACKING_ID), -1)

                uhdev.destroy()

        def test_mt_contact_count_accurate(self):
            """Test the MT_QUIRK_CONTACT_CNT_ACCURATE from the kernel.
            A report should forward an accurate contact count and the kernel
            should ignore any data provided after we have reached this
            contact count."""
            with self.__create_device() as uhdev:
                if uhdev.quirks is not None and 'CONTACT_CNT_ACCURATE' not in uhdev.quirks:
                    uhdev.destroy()
                    raise unittest.SkipTest('Device not compatible')

                if uhdev.touches_in_a_report == 1:
                    uhdev.destroy()
                    raise unittest.SkipTest('Device not compatible, we can not trigger the conditions')

                while uhdev.application not in uhdev.input_nodes:
                    uhdev.process_one_event(10)

                t0 = Touch(1, 5, 10)
                t1 = Touch(2, 15, 20)

                r = uhdev.event([t0, t1], contact_count=1)
                self.debug_reports(r, uhdev)
                events = uhdev.next_sync_events()
                self.debug_reports(r, uhdev); print(events)
                self.assertIn(libevdev.InputEvent(libevdev.EV_KEY.BTN_TOUCH, 1), events)
                self.assertEqual(uhdev.evdev.value[libevdev.EV_KEY.BTN_TOUCH], 1)
                self.assertIn(libevdev.InputEvent(libevdev.EV_ABS.ABS_MT_TRACKING_ID, 0), events)
                self.assertEqual(uhdev.evdev.slot_value(0, libevdev.EV_ABS.ABS_MT_TRACKING_ID), 0)
                self.assertEqual(uhdev.evdev.slot_value(0, libevdev.EV_ABS.ABS_MT_POSITION_X), 5)
                self.assertEqual(uhdev.evdev.slot_value(0, libevdev.EV_ABS.ABS_MT_POSITION_Y), 10)
                self.assertEqual(uhdev.evdev.slot_value(1, libevdev.EV_ABS.ABS_MT_TRACKING_ID), -1)

                uhdev.destroy()

    class TestWin8Multitouch(TestMultitouch):
        def __init__(self, methodName='runTest'):
            super(BaseTest.TestWin8Multitouch, self).__init__(methodName)
            self.__create_device = self._create_device

        def test_mt_tx_cx(self):
            """send a single touch in the first slot of the device, with
            different values of Tx and Cx. Make sure the kernel reports Tx."""
            with self.__create_device() as uhdev:
                if uhdev.fields.count('X') == uhdev.touches_in_a_report:
                    # there is not point testing those
                    uhdev.destroy()
                    raise unittest.SkipTest('Device not compatible, we can not trigger the conditions')

                while uhdev.application not in uhdev.input_nodes:
                    uhdev.process_one_event(10)

                t0 = Touch(1, 5, 10)
                t0.cx = 50
                t0.cy = 100
                r = uhdev.event([t0])
                events = uhdev.next_sync_events()
                self.debug_reports(r, uhdev); print(events)
                self.assertIn(libevdev.InputEvent(libevdev.EV_KEY.BTN_TOUCH, 1), events)
                self.assertEqual(uhdev.evdev.slot_value(0, libevdev.EV_ABS.ABS_MT_TRACKING_ID), 0)
                self.assertEqual(uhdev.evdev.slot_value(0, libevdev.EV_ABS.ABS_MT_POSITION_X), 5)
                self.assertEqual(uhdev.evdev.slot_value(0, libevdev.EV_ABS.ABS_MT_TOOL_X), 50)
                self.assertEqual(uhdev.evdev.slot_value(0, libevdev.EV_ABS.ABS_MT_POSITION_Y), 10)
                self.assertEqual(uhdev.evdev.slot_value(0, libevdev.EV_ABS.ABS_MT_TOOL_Y), 100)

                uhdev.destroy()

        def test_mt_inrange(self):
            """Send one contact that has the InRange bit set before/after
            tipswitch.
            Kernel is supposed to mark the contact with a distance > 0
            when inrange is set but not tipswitch.

            This tests the hovering capability of devices (MT_QUIRK_HOVERING).

            Make sure the contact is only released from the kernel POV
            when the inrange bit is set to 0."""
            with self.__create_device() as uhdev:
                if 'In Range' not in uhdev.fields:
                    uhdev.destroy()
                    raise unittest.SkipTest('Device not compatible, missing In Range usage')

                while uhdev.application not in uhdev.input_nodes:
                    uhdev.process_one_event(10)

                t0 = Touch(1, 150, 200)
                t0.tipswitch = False
                r = uhdev.event([t0])
                events = uhdev.next_sync_events()
                self.debug_reports(r, uhdev); print(events)
                self.assertIn(libevdev.InputEvent(libevdev.EV_KEY.BTN_TOUCH, 1), events)
                self.assertEqual(uhdev.evdev.value[libevdev.EV_KEY.BTN_TOUCH], 1)
                self.assertIn(libevdev.InputEvent(libevdev.EV_ABS.ABS_MT_TRACKING_ID, 0), events)
                self.assertIn(libevdev.InputEvent(libevdev.EV_ABS.ABS_MT_DISTANCE), events)
                self.assertGreater(uhdev.evdev.slot_value(0, libevdev.EV_ABS.ABS_MT_DISTANCE), 0)
                self.assertEqual(uhdev.evdev.slot_value(0, libevdev.EV_ABS.ABS_MT_TRACKING_ID), 0)
                self.assertEqual(uhdev.evdev.slot_value(0, libevdev.EV_ABS.ABS_MT_POSITION_X), 150)
                self.assertEqual(uhdev.evdev.slot_value(0, libevdev.EV_ABS.ABS_MT_POSITION_Y), 200)
                self.assertEqual(uhdev.evdev.slot_value(1, libevdev.EV_ABS.ABS_MT_TRACKING_ID), -1)

                t0.tipswitch = True
                r = uhdev.event([t0])
                events = uhdev.next_sync_events()
                self.debug_reports(r, uhdev); print(events)
                self.assertIn(libevdev.InputEvent(libevdev.EV_ABS.ABS_MT_DISTANCE, 0), events)
                self.assertEqual(uhdev.evdev.slot_value(0, libevdev.EV_ABS.ABS_MT_DISTANCE), 0)

                t0.tipswitch = False
                r = uhdev.event([t0])
                events = uhdev.next_sync_events()
                self.debug_reports(r, uhdev); print(events)
                self.assertIn(libevdev.InputEvent(libevdev.EV_ABS.ABS_MT_DISTANCE), events)
                self.assertGreater(uhdev.evdev.slot_value(0, libevdev.EV_ABS.ABS_MT_DISTANCE), 0)

                t0.inrange = False
                r = uhdev.event([t0])
                events = uhdev.next_sync_events()
                self.debug_reports(r, uhdev); print(events)
                self.assertIn(libevdev.InputEvent(libevdev.EV_KEY.BTN_TOUCH, 0), events)
                self.assertEqual(uhdev.evdev.slot_value(0, libevdev.EV_ABS.ABS_MT_TRACKING_ID), -1)

                uhdev.destroy()

        def test_mt_duplicates(self):
            """Test the MT_QUIRK_IGNORE_DUPLICATES from the kernel.
            If a touch is reported more than once with the same Contact ID,
            we should only handle the first touch.

            Note: this is not in MS spec, but the current kernel behaves
            like that"""
            with self.__create_device() as uhdev:
                while uhdev.application not in uhdev.input_nodes:
                    uhdev.process_one_event(10)

                t0 = Touch(1, 5, 10)
                t1 = Touch(1, 15, 20)
                t2 = Touch(2, 50, 100)

                r = uhdev.event([t0, t1, t2], contact_count=2)
                events = uhdev.next_sync_events()
                self.debug_reports(r, uhdev); print(events)
                self.assertIn(libevdev.InputEvent(libevdev.EV_KEY.BTN_TOUCH, 1), events)
                self.assertEqual(uhdev.evdev.value[libevdev.EV_KEY.BTN_TOUCH], 1)
                self.assertIn(libevdev.InputEvent(libevdev.EV_ABS.ABS_MT_TRACKING_ID, 0), events)
                self.assertEqual(uhdev.evdev.slot_value(0, libevdev.EV_ABS.ABS_MT_TRACKING_ID), 0)
                self.assertEqual(uhdev.evdev.slot_value(0, libevdev.EV_ABS.ABS_MT_POSITION_X), 5)
                self.assertEqual(uhdev.evdev.slot_value(0, libevdev.EV_ABS.ABS_MT_POSITION_Y), 10)
                self.assertEqual(uhdev.evdev.slot_value(1, libevdev.EV_ABS.ABS_MT_TRACKING_ID), 1)
                self.assertEqual(uhdev.evdev.slot_value(1, libevdev.EV_ABS.ABS_MT_POSITION_X), 50)
                self.assertEqual(uhdev.evdev.slot_value(1, libevdev.EV_ABS.ABS_MT_POSITION_Y), 100)

                uhdev.destroy()

        def test_mt_release_miss(self):
            """send a single touch in the first slot of the device, and
            forget to release it. The kernel is supposed to release by itself
            the touch in 100ms.
            Make sure that we are dealing with a new touch by resending the
            same touch after the timeout expired, and check that the kernel
            considers it as a separate touch (different tracking ID)"""
            with self.__create_device() as uhdev:
                while uhdev.application not in uhdev.input_nodes:
                    uhdev.process_one_event(10)

                t0 = Touch(1, 5, 10)
                r = uhdev.event([t0])
                events = uhdev.next_sync_events()
                self.debug_reports(r, uhdev); print(events)
                self.assertEqual(uhdev.evdev.slot_value(0, libevdev.EV_ABS.ABS_MT_TRACKING_ID), 0)

                time.sleep(0.12)
                events = uhdev.next_sync_events()
                self.debug_reports(r, uhdev); print(events)
                self.assertIn(libevdev.InputEvent(libevdev.EV_KEY.BTN_TOUCH, 0), events)
                self.assertEqual(uhdev.evdev.slot_value(0, libevdev.EV_ABS.ABS_MT_TRACKING_ID), -1)

                r = uhdev.event([t0])
                events = uhdev.next_sync_events()
                self.debug_reports(r, uhdev); print(events)
                self.assertEqual(uhdev.evdev.slot_value(0, libevdev.EV_ABS.ABS_MT_TRACKING_ID), 1)
                uhdev.destroy()

        def test_mt_azimuth(self):
            """Check for the azimtuh information bit.
            When azimuth is presented by the device, it should be exported
            as ABS_MT_ORIENTATION and the exported value should report a quarter
            of circle."""
            with self.__create_device() as uhdev:
                if 'Azimuth' not in uhdev.fields:
                    uhdev.destroy()
                    raise unittest.SkipTest('Device not compatible, missing Azimuth usage')

                while uhdev.application not in uhdev.input_nodes:
                    uhdev.process_one_event(10)

                t0 = Touch(1, 5, 10)
                t0.azimuth = 270

                r = uhdev.event([t0])
                events = uhdev.next_sync_events()
                self.debug_reports(r, uhdev); print(events)

                # orientation is clockwise, while Azimuth is counter clockwise
                self.assertIn(libevdev.InputEvent(libevdev.EV_ABS.ABS_MT_ORIENTATION, 90), events)

                uhdev.destroy()


    class TestPTP(TestMultitouch):
        def __init__(self, methodName='runTest'):
            super(BaseTest.TestPTP, self).__init__(methodName)
            self.__create_device = self._create_device

        def assertName(self, uhdev):
            self.assertIn(uhdev.name, uhdev.evdev.name)

        def test_ptp_buttons(self):
            """check for button reliability.
            There are 2 types of touchpads: the click pads and the pressure pads.
            Each should reliably report the BTN_LEFT events.
            """
            with self.__create_device() as uhdev:
                while uhdev.application not in uhdev.input_nodes:
                    uhdev.process_one_event(10)

                if uhdev.type == 'clickpad':
                    r = uhdev.event(click=True)
                    events = uhdev.next_sync_events()
                    self.debug_reports(r, uhdev); print(events)
                    self.assertIn(libevdev.InputEvent(libevdev.EV_KEY.BTN_LEFT, 1), events)
                    self.assertEqual(uhdev.evdev.value[libevdev.EV_KEY.BTN_LEFT], 1)

                    r = uhdev.event(click=False)
                    events = uhdev.next_sync_events()
                    self.debug_reports(r, uhdev); print(events)
                    self.assertIn(libevdev.InputEvent(libevdev.EV_KEY.BTN_LEFT, 0), events)
                    self.assertEqual(uhdev.evdev.value[libevdev.EV_KEY.BTN_LEFT], 0)
                else:
                    r = uhdev.event(left=True)
                    events = uhdev.next_sync_events()
                    self.debug_reports(r, uhdev); print(events)
                    self.assertIn(libevdev.InputEvent(libevdev.EV_KEY.BTN_LEFT, 1), events)
                    self.assertEqual(uhdev.evdev.value[libevdev.EV_KEY.BTN_LEFT], 1)

                    r = uhdev.event(left=False)
                    events = uhdev.next_sync_events()
                    self.debug_reports(r, uhdev); print(events)
                    self.assertIn(libevdev.InputEvent(libevdev.EV_KEY.BTN_LEFT, 0), events)
                    self.assertEqual(uhdev.evdev.value[libevdev.EV_KEY.BTN_LEFT], 0)

                    r = uhdev.event(right=True)
                    events = uhdev.next_sync_events()
                    self.debug_reports(r, uhdev); print(events)
                    self.assertIn(libevdev.InputEvent(libevdev.EV_KEY.BTN_RIGHT, 1), events)
                    self.assertEqual(uhdev.evdev.value[libevdev.EV_KEY.BTN_RIGHT], 1)

                    r = uhdev.event(right=False)
                    events = uhdev.next_sync_events()
                    self.debug_reports(r, uhdev); print(events)
                    self.assertIn(libevdev.InputEvent(libevdev.EV_KEY.BTN_RIGHT, 0), events)
                    self.assertEqual(uhdev.evdev.value[libevdev.EV_KEY.BTN_RIGHT], 0)

        def test_ptp_confidence(self):
            """Check for the validity of the confidence bit.
            When a contact is marked as not confident, it should be detected
            as a palm from the kernel POV and released.

            Note: shouldn't the kernel use ABS_MT_TOOL_PALM instead of
            blindly releasing it?"""
            with self.__create_device() as uhdev:
                if 'Confidence' not in uhdev.fields:
                    uhdev.destroy()
                    raise unittest.SkipTest('Device not compatible, missing Confidence usage')

                while uhdev.application not in uhdev.input_nodes:
                    uhdev.process_one_event(10)

                t0 = Touch(1, 150, 200)
                r = uhdev.event([t0])
                events = uhdev.next_sync_events()
                self.debug_reports(r, uhdev); print(events)

                t0.confidence = False
                r = uhdev.event([t0])
                events = uhdev.next_sync_events()
                self.debug_reports(r, uhdev); print(events)
                self.assertIn(libevdev.InputEvent(libevdev.EV_KEY.BTN_TOUCH, 0), events)
                self.assertEqual(uhdev.evdev.slot_value(0, libevdev.EV_ABS.ABS_MT_TRACKING_ID), -1)

                uhdev.destroy()

        def test_ptp_non_touch_data(self):
            """Some single finger hybrid touchpads might not provide the
            button information in subsequent reports (only in the first report).

            Emulate this and make sure we do not release the buttons in the
            middle of the event."""
            with self.__create_device() as uhdev:
                if uhdev.touches_in_a_report >= uhdev.max_contacts:
                    # there is not point testing those
                    uhdev.destroy()
                    raise unittest.SkipTest('Device not compatible, we can not trigger the conditions')

                while uhdev.application not in uhdev.input_nodes:
                    uhdev.process_one_event(10)

                touches = [Touch(i, i * 10, i * 10 + 5) for i in range(uhdev.max_contacts)]
                contact_count = uhdev.max_contacts
                incr_scantime = True
                btn_state = True
                events = None
                while touches:
                    t = touches[:uhdev.touches_in_a_report]
                    touches = touches[uhdev.touches_in_a_report:]
                    r = uhdev.event(t, click=btn_state, left=btn_state, contact_count=contact_count, incr_scantime=incr_scantime)
                    contact_count = 0
                    incr_scantime = False
                    btn_state = False
                    events = uhdev.next_sync_events()
                    self.debug_reports(r, uhdev); print(events)
                    if touches:
                        self.assertEqual(len(events), 0)

                self.assertIn(libevdev.InputEvent(libevdev.EV_KEY.BTN_LEFT, 1), events)
                self.assertNotIn(libevdev.InputEvent(libevdev.EV_KEY.BTN_LEFT, 0), events)
                self.assertEqual(uhdev.evdev.value[libevdev.EV_KEY.BTN_LEFT], 1)

                uhdev.destroy()


################################################################################
#
# Windows 7 compatible devices
#
################################################################################

class Test3m_0596_0500(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test 3m_0596_0500',
                         rdesc='05 01 09 01 a1 01 85 01 09 01 a1 00 05 09 09 01 95 01 75 01 15 00 25 01 81 02 95 07 75 01 81 03 95 01 75 08 81 03 05 01 09 30 09 31 15 00 26 ff 7f 35 00 46 00 00 95 02 75 10 81 02 c0 a1 02 15 00 26 ff 00 09 01 95 39 75 08 81 01 c0 c0 05 0d 09 0e a1 01 85 11 09 23 a1 02 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0 09 04 a1 01 85 10 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 3a 06 81 02 09 31 46 e8 03 81 02 c0 05 0d a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 3a 06 81 02 09 31 46 e8 03 81 02 c0 05 0d a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 3a 06 81 02 09 31 46 e8 03 81 02 c0 05 0d a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 3a 06 81 02 09 31 46 e8 03 81 02 c0 05 0d a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 3a 06 81 02 09 31 46 e8 03 81 02 c0 05 0d a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 3a 06 81 02 09 31 46 e8 03 81 02 c0 05 0d a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 3a 06 81 02 09 31 46 e8 03 81 02 c0 05 0d a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 3a 06 81 02 09 31 46 e8 03 81 02 c0 05 0d a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 3a 06 81 02 09 31 46 e8 03 81 02 c0 05 0d a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 3a 06 81 02 09 31 46 e8 03 81 02 c0 05 0d 09 54 95 01 75 08 15 00 25 0a 81 02 85 12 09 55 95 01 75 08 15 00 25 0a b1 02 06 00 ff 15 00 26 ff 00 85 03 09 01 75 08 95 07 b1 02 85 04 09 01 75 08 95 17 b1 02 85 05 09 01 75 08 95 47 b1 02 85 06 09 01 75 08 95 07 b1 02 85 07 09 01 75 08 95 07 b1 02 85 08 09 01 75 08 95 07 b1 02 85 09 09 01 75 08 95 3f b1 02 c0',
                         info=(0x3, 0x0596, 0x0500),
                         max_contacts=60,
                         quirks=('VALID_IS_CONFIDENCE', 'SLOT_IS_CONTACTID', 'TOUCH_SIZE_SCALING'))


class Test3m_0596_0506(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test 3m_0596_0506',
                         rdesc='05 01 09 01 a1 01 85 01 09 01 a1 00 05 09 09 01 95 01 75 01 15 00 25 01 81 02 95 07 75 01 81 03 95 01 75 08 81 03 05 01 09 30 09 31 15 00 26 ff 7f 35 00 46 00 00 95 02 75 10 81 02 c0 a1 02 15 00 26 ff 00 09 01 95 39 75 08 81 03 c0 c0 05 0d 09 0e a1 01 85 11 09 23 a1 02 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0 09 04 a1 01 85 13 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 d6 0a 81 02 09 31 46 22 06 81 02 05 0d 75 10 95 01 09 48 81 02 09 49 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 d6 0a 81 02 09 31 46 22 06 81 02 05 0d 75 10 95 01 09 48 81 02 09 49 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 d6 0a 81 02 09 31 46 22 06 81 02 05 0d 75 10 95 01 09 48 81 02 09 49 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 d6 0a 81 02 09 31 46 22 06 81 02 05 0d 75 10 95 01 09 48 81 02 09 49 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 d6 0a 81 02 09 31 46 22 06 81 02 05 0d 75 10 95 01 09 48 81 02 09 49 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 d6 0a 81 02 09 31 46 22 06 81 02 05 0d 75 10 95 01 09 48 81 02 09 49 81 02 c0 05 0d 09 54 95 01 75 08 15 00 25 3c 81 02 06 00 ff 09 01 15 00 26 ff 00 75 08 95 02 81 03 05 0d 85 12 09 55 95 01 75 08 15 00 25 3c b1 02 06 00 ff 15 00 26 ff 00 85 03 09 01 75 08 95 07 b1 02 85 04 09 01 75 08 95 17 b1 02 85 05 09 01 75 08 95 47 b1 02 85 06 09 01 75 08 95 07 b1 02 85 73 09 01 75 08 95 07 b1 02 85 08 09 01 75 08 95 07 b1 02 85 09 09 01 75 08 95 3f b1 02 85 0f 09 01 75 08 96 07 02 b1 02 c0',
                         info=(0x3, 0x0596, 0x0506),
                         max_contacts=60,
                         quirks=('VALID_IS_CONFIDENCE', 'SLOT_IS_CONTACTID', 'TOUCH_SIZE_SCALING'))


class TestActionStar_2101_1011(BaseTest.TestMultitouch):
    def __init__(self, methodName='runTest'):
        super(TestActionStar_2101_1011, self).__init__(methodName)
        self.__create_device = self._create_device

    def _create_device(self):
        return Digitizer('uhid test ActionStar_2101_1011',
                         rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 09 51 75 08 95 01 81 02 05 01 35 00 55 0e 65 33 75 10 95 01 09 30 26 ff 4d 46 70 03 81 02 09 31 26 ff 2b 46 f1 01 81 02 46 00 00 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 09 51 75 08 95 01 81 02 05 01 35 00 55 0e 65 33 75 10 95 01 09 30 26 ff 4d 46 70 03 81 02 09 31 26 ff 2b 46 f1 01 81 02 46 00 00 c0 05 0d 09 54 75 08 95 01 81 02 05 0d 85 02 09 55 25 02 75 08 95 01 b1 02 c0',
                         info=(0x3, 0x2101, 0x1011))

    def test_mt_actionstar_inrange(self):
        """Special sequence that might not be handled properly"""
        with self.__create_device() as uhdev:
            while uhdev.application not in uhdev.input_nodes:
                uhdev.process_one_event(10)

            sequence = [
                # t0 = Touch(1, 6999, 2441) | t1 = Touch(2, 15227, 2026)
                '01 ff 01 57 1b 89 09 ff 02 7b 3b ea 07 02',
                # t0.xy = (6996, 2450)      | t1.y = 2028
                '01 ff 01 54 1b 92 09 ff 02 7b 3b ec 07 02',
                # t1.xy = (15233, 2040)     | t0.tipswitch = False
                '01 ff 02 81 3b f8 07 fe 01 54 1b 92 09 02',
                # t1                        | t0.inrange = False
                '01 ff 02 81 3b f8 07 fc 01 54 1b 92 09 02',
            ]

            for num, r_str in enumerate(sequence):
                r = [int(i, 16) for i in r_str.split()]
                uhdev.call_input_event(r)
                events = uhdev.next_sync_events()
                self.debug_reports([r], uhdev);
                for e in events: print(e)
                if num == 2:
                    self.assertEqual(uhdev.evdev.slot_value(0, libevdev.EV_ABS.ABS_MT_TRACKING_ID), -1)

            uhdev.destroy()


class TestAtmel_03eb_201c(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test atmel_03eb_201c',
                         rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 09 51 75 08 95 01 81 02 05 01 35 00 55 0e 65 33 75 10 95 01 09 30 26 ff 4b 46 70 03 81 02 09 31 26 ff 2b 46 f1 01 81 02 46 00 00 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 09 51 75 08 95 01 81 02 05 01 35 00 55 0e 65 33 75 10 95 01 09 30 26 ff 4b 46 70 03 81 02 09 31 26 ff 2b 46 f1 01 81 02 46 00 00 c0 05 0d 09 54 75 08 95 01 81 02 05 0d 85 02 09 55 25 02 75 08 95 01 b1 02 c0',
                         info=(0x3, 0x03eb, 0x201c))


class TestAtmel_03eb_211c(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test atmel_03eb_211c',
                         rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 00 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 37 81 02 25 1f 75 05 09 51 81 02 05 01 55 0e 65 11 35 00 75 10 46 56 0a 26 ff 0f 09 30 81 02 46 b2 05 26 ff 0f 09 31 81 02 05 0d 75 08 85 02 09 55 25 10 b1 02 c0 c0',
                         info=(0x3, 0x03eb, 0x211c))


class TestCando_2087_0a02(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test cando_2087_0a02',
                         rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 0f 75 10 55 0e 65 33 09 30 35 00 46 6d 03 81 02 46 ec 01 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 0f 75 10 55 0e 65 33 09 30 35 00 46 6d 03 81 02 46 ec 01 09 31 81 02 c0 05 0d 09 54 95 01 75 08 15 00 25 02 81 02 85 02 09 55 b1 02 c0 06 00 ff 09 01 a1 01 85 a6 95 22 75 08 26 ff 00 15 00 09 01 81 02 85 a5 95 06 75 08 26 ff 00 15 00 09 01 91 02 c0',
                         info=(0x3, 0x2087, 0x0a02))


class TestCando_2087_0b03(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test cando_2087_0b03',
                         rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 09 51 75 08 95 01 81 02 05 01 35 00 55 0e 65 33 75 10 95 01 09 30 26 ff 49 46 f2 03 81 02 09 31 26 ff 29 46 39 02 81 02 46 00 00 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 09 51 75 08 95 01 81 02 05 01 35 00 55 0e 65 33 75 10 95 01 09 30 26 ff 49 46 f2 03 81 02 09 31 26 ff 29 46 39 02 81 02 46 00 00 c0 05 0d 09 54 75 08 95 01 81 02 05 0d 85 02 09 55 25 02 75 08 95 01 b1 02 c0',
                         info=(0x3, 0x2087, 0x0b03))


class TestCvtouch_1ff7_0017(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test cvtouch_1ff7_0017',
                         rdesc='06 00 ff 09 00 a1 01 85 fd 06 00 ff 09 01 09 02 09 03 09 04 09 05 09 06 15 00 26 ff 00 75 08 95 06 81 02 85 fe 06 00 ff 09 01 09 02 09 03 09 04 15 00 26 ff 00 75 08 95 04 b1 02 c0 05 01 09 02 a1 01 09 01 a1 00 85 01 05 09 19 01 29 03 15 00 25 01 95 03 75 01 81 02 95 01 75 05 81 03 05 01 09 30 09 31 15 00 26 ff 0f 35 00 46 ff 0f 75 10 95 02 81 02 09 00 15 00 25 ff 35 00 45 ff 75 08 95 01 81 02 09 38 15 81 25 7f 95 01 81 06 c0 c0 06 00 ff 09 00 a1 01 85 fc 15 00 25 ff 19 01 29 3f 75 08 95 3f 81 02 19 01 29 3f 91 02 c0 06 00 ff 09 00 a1 01 85 fb 15 00 25 ff 19 01 29 3f 75 08 95 3f 81 02 19 01 29 3f 91 02 c0 05 0d 09 04 a1 01 85 02 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 15 00 26 ff 0f 75 10 55 00 65 00 09 30 35 00 46 ff 0f 81 02 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 15 00 26 ff 0f 75 10 55 00 65 00 09 30 35 00 46 ff 0f 81 02 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 15 00 26 ff 0f 75 10 55 00 65 00 09 30 35 00 46 ff 0f 81 02 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 15 00 26 ff 0f 75 10 55 00 65 00 09 30 35 00 46 ff 0f 81 02 09 31 81 02 c0 05 0d 09 54 95 01 75 08 81 02 85 03 09 55 25 02 b1 02 c0 09 0e a1 01 85 04 09 23 a1 02 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0',
                         info=(0x3, 0x1ff7, 0x0017))


class TestCypress_04b4_c001(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test cypress_04b4_c001',
                         rdesc='05 01 09 02 a1 01 85 01 09 01 a1 00 05 09 19 01 29 03 15 00 25 01 95 03 75 01 81 02 95 01 75 05 81 01 05 01 09 30 09 31 15 81 25 7f 75 08 95 02 81 06 c0 c0 05 0d 09 04 a1 01 85 02 09 22 09 53 95 01 75 08 81 02 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 15 00 25 20 09 48 81 02 09 49 81 02 05 01 15 00 26 d0 07 75 10 55 00 65 00 09 30 15 00 26 d0 07 35 00 45 00 81 02 09 31 45 00 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 15 00 25 20 09 48 81 02 09 49 81 02 05 01 15 00 26 d0 07 75 10 55 00 65 00 09 30 15 00 26 d0 07 35 00 45 00 81 02 09 31 45 00 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 15 00 25 20 09 48 81 02 09 49 81 02 05 01 15 00 26 d0 07 75 10 55 00 65 00 09 30 15 00 26 d0 07 35 00 45 00 81 02 09 31 45 00 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 15 00 25 20 09 48 81 02 09 49 81 02 05 01 15 00 26 d0 07 75 10 55 00 65 00 09 30 15 00 26 d0 07 35 00 45 00 81 02 09 31 45 00 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 15 00 25 20 09 48 81 02 09 49 81 02 05 01 15 00 26 d0 07 75 10 55 00 65 00 09 30 15 00 26 d0 07 35 00 45 00 81 02 09 31 45 00 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 15 00 25 20 09 48 81 02 09 49 81 02 05 01 15 00 26 d0 07 75 10 55 00 65 00 09 30 15 00 26 d0 07 35 00 45 00 81 02 09 31 45 00 81 02 c0 05 0d 09 54 95 01 75 08 15 00 25 0a 81 02 09 55 b1 02 c0 09 0e a1 01 85 03 09 23 a1 02 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0',
                         info=(0x3, 0x04b4, 0xc001))


class TestData_modul_7374_1232(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test data-modul_7374_1232',
                         rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 00 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 37 81 02 25 1f 75 05 09 51 81 02 05 01 55 0e 65 11 35 00 75 10 46 d0 07 26 ff 0f 09 30 81 02 46 40 06 09 31 81 02 05 0d 75 08 85 02 09 55 25 10 b1 02 c0 c0',
                         info=(0x3, 0x7374, 0x1232))


class TestData_modul_7374_1252(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test data-modul_7374_1252',
                         rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 00 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 37 81 02 25 1f 75 05 09 51 81 02 05 01 55 0e 65 11 35 00 75 10 46 d0 07 26 ff 0f 09 30 81 02 46 40 06 09 31 81 02 05 0d 75 08 85 02 09 55 25 10 b1 02 c0 c0',
                         info=(0x3, 0x7374, 0x1252))


class TestE4_2219_044c(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test e4_2219_044c',
                         rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 00 65 00 09 30 35 00 46 00 00 81 02 09 31 46 00 00 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 00 65 00 09 30 35 00 46 00 00 81 02 09 31 46 00 00 81 02 c0 05 0d 09 54 95 01 75 08 15 00 25 08 81 02 09 55 b1 02 c0 09 0e a1 01 85 02 09 23 a1 02 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0 05 01 09 02 a1 01 85 03 09 01 a1 00 05 09 19 01 29 03 15 00 25 01 95 03 75 01 81 02 95 01 75 05 81 01 05 01 09 30 09 31 15 00 26 ff 7f 75 10 95 02 81 02 05 01 09 38 15 81 25 7f 75 08 95 01 81 06 c0 c0',
                         info=(0x3, 0x2219, 0x044c))


class TestElo_touchsystems_04e7_0022(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test elo-touchsystems_04e7_0022',
                         rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 0f 75 10 55 0e 65 33 09 30 35 00 46 ff 0f 81 02 46 ff 0f 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 0f 75 10 55 00 65 00 09 30 35 00 46 ff 0f 81 02 46 ff 0f 09 31 81 02 c0 05 0d 09 54 25 10 95 01 75 08 81 02 85 08 09 55 25 02 b1 02 c0 09 0e a1 01 85 07 09 22 a1 00 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 06 00 ff 09 55 85 80 15 00 26 ff 00 75 08 95 01 b1 82 c0 05 01 09 02 a1 01 85 54 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 75 01 95 02 81 02 95 06 81 03 05 01 09 30 15 00 26 ff 0f 75 10 95 01 81 02 09 31 75 10 95 01 81 02 09 3b 16 00 00 26 00 01 36 00 00 46 00 01 66 00 00 75 10 95 01 81 62 c0 c0',
                         info=(0x3, 0x04e7, 0x0022))


class TestHanvon_20b3_0a18(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test hanvon_20b3_0a18',
                         rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 09 51 75 08 95 01 81 02 05 01 35 00 55 0e 65 33 75 10 95 01 09 30 26 ff 4b 46 70 03 81 02 09 31 26 ff 2b 46 f1 01 81 02 46 00 00 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 09 51 75 08 95 01 81 02 05 01 35 00 55 0e 65 33 75 10 95 01 09 30 26 ff 4b 46 70 03 81 02 09 31 26 ff 2b 46 f1 01 81 02 46 00 00 c0 05 0d 09 54 75 08 95 01 81 02 05 0d 85 02 09 55 25 02 75 08 95 01 b1 02 c0',
                         info=(0x3, 0x20b3, 0x0a18))


class TestHuitoo_03f7_0003(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test huitoo_03f7_0003',
                         rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 00 65 00 35 00 46 ff 0f 09 30 26 ff 0f 81 02 09 31 26 ff 0f 81 02 05 0d 09 48 26 ff 0f 81 02 09 49 26 ff 0f 81 02 c0 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 00 65 00 35 00 46 ff 0f 09 30 26 ff 0f 81 02 09 31 26 ff 0f 81 02 05 0d 09 48 26 ff 0f 81 02 09 49 26 ff 0f 81 02 c0 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 00 65 00 35 00 46 ff 0f 09 30 26 ff 0f 81 02 09 31 26 ff 0f 81 02 05 0d 09 48 26 ff 0f 81 02 09 49 26 ff 0f 81 02 c0 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 00 65 00 35 00 46 ff 0f 09 30 26 ff 0f 81 02 09 31 26 ff 0f 81 02 05 0d 09 48 26 ff 0f 81 02 09 49 26 ff 0f 81 02 c0 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 00 65 00 35 00 46 ff 0f 09 30 26 ff 0f 81 02 09 31 26 ff 0f 81 02 05 0d 09 48 26 ff 0f 81 02 09 49 26 ff 0f 81 02 c0 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 00 65 00 35 00 46 ff 0f 09 30 26 ff 0f 81 02 09 31 26 ff 0f 81 02 05 0d 09 48 26 ff 0f 81 02 09 49 26 ff 0f 81 02 c0 05 0d 09 54 95 01 75 08 15 00 25 08 81 02 09 55 b1 02 c0 09 0e a1 01 85 02 09 23 a1 02 09 52 09 53 15 00 25 10 75 08 95 02 b1 02 c0 c0 05 01 09 02 a1 01 85 03 09 01 a1 00 05 09 19 01 29 03 15 00 25 01 95 03 75 01 81 02 95 01 75 05 81 01 05 01 09 30 09 31 15 00 26 ff 0f 35 00 46 ff 0f 75 10 95 02 81 02 c0 c0 06 00 ff 09 01 a1 01 85 04 15 00 26 ff 00 75 08 95 3f 09 02 81 02 95 3f 09 02 91 02 c0',
                         info=(0x3, 0x03f7, 0x0003))


class TestIdeacom_1cb6_6650(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test ideacom_1cb6_6650',
                         rdesc='05 0d 09 04 a1 01 85 0a 09 22 a1 00 09 42 09 32 15 00 25 01 95 02 75 01 81 02 95 06 81 03 05 01 26 ff 1f 75 10 95 01 55 0d 65 33 09 31 35 00 46 61 13 81 02 09 30 46 73 22 81 02 05 0d 75 08 95 01 09 30 26 ff 00 81 02 09 51 81 02 85 0c 09 55 25 02 95 01 b1 02 c0 06 00 ff 85 02 09 01 75 08 95 07 b1 02 85 03 09 02 75 08 95 07 b1 02 85 04 09 03 75 08 95 07 b1 02 85 05 09 04 75 08 95 07 b1 02 85 06 09 05 75 08 96 27 00 b1 02 85 07 09 06 75 08 96 27 00 b1 02 85 08 09 07 75 08 95 07 b1 02 85 09 09 08 75 08 95 07 b1 02 85 0b 09 09 75 08 96 07 00 b1 02 85 0d 09 0a 75 08 96 27 00 b1 02 c0 09 0e a1 01 85 0e 09 52 09 53 95 07 b1 02 c0 05 01 09 02 a1 01 85 01 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 75 01 95 02 81 02 75 06 95 01 81 01 05 01 09 31 09 30 15 00 27 ff 1f 00 00 75 10 95 02 81 02 c0 09 01 a1 02 15 00 26 ff 00 95 02 75 08 81 03 c0 c0',
                         info=(0x3, 0x1cb6, 0x6650))


class TestIdeacom_1cb6_6651(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test ideacom_1cb6_6651',
                         rdesc='05 0d 09 04 a1 01 85 0a 09 22 a1 02 09 42 09 32 15 00 25 01 95 02 75 01 81 02 95 06 81 03 05 01 26 ff 1f 75 10 95 01 55 0d 65 33 09 31 35 00 46 39 13 81 02 09 30 46 24 22 81 02 05 0d 75 08 95 01 09 30 26 ff 00 81 02 09 51 81 02 85 0c 09 55 25 02 95 01 b1 02 c0 06 00 ff 85 02 09 01 75 08 95 07 b1 02 85 03 09 02 75 08 95 07 b1 02 85 04 09 03 75 08 95 07 b1 02 85 05 09 04 75 08 95 07 b1 02 85 06 09 05 75 08 95 1f b1 02 85 07 09 06 75 08 96 1f 00 b1 02 85 08 09 07 75 08 95 07 b1 02 85 09 09 08 75 08 95 07 b1 02 85 0b 09 09 75 08 95 07 b1 02 85 0d 09 0a 75 08 96 1f 00 b1 02 c0 09 0e a1 01 85 0e 09 52 09 53 95 07 b1 02 c0 05 01 09 02 a1 01 85 01 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 75 01 95 02 81 02 75 06 95 01 81 01 05 01 09 31 09 30 15 00 27 ff 1f 00 00 75 10 95 02 81 02 c0 09 01 a1 02 15 00 26 ff 00 95 02 75 08 81 03 c0 c0',
                         info=(0x3, 0x1cb6, 0x6651))


class TestIkaist_2793_0001(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test ikaist_2793_0001',
                         rdesc='05 01 09 01 a1 01 85 01 09 01 a1 00 05 09 09 01 95 01 75 01 15 00 25 01 81 02 95 07 75 01 81 03 95 01 75 08 81 03 05 01 09 30 09 31 15 00 26 ff 7f 35 00 46 00 00 95 02 75 10 81 02 c0 a1 02 15 00 26 ff 00 09 01 95 39 75 08 81 03 c0 c0 05 0d 09 0e a1 01 85 11 09 23 a1 02 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0 09 04 a1 01 85 13 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 51 07 81 02 09 31 46 96 04 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 51 07 81 02 09 31 46 96 04 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 51 07 81 02 09 31 46 96 04 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 51 07 81 02 09 31 46 96 04 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 51 07 81 02 09 31 46 96 04 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 51 07 81 02 09 31 46 96 04 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 51 07 81 02 09 31 46 96 04 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 51 07 81 02 09 31 46 96 04 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 51 07 81 02 09 31 46 96 04 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 33 09 30 35 00 46 51 07 81 02 09 31 46 96 04 81 02 c0 05 0d 09 54 95 01 75 08 15 00 25 3c 81 02 06 00 ff 09 01 15 00 26 ff 00 75 08 95 02 81 03 05 0d 85 12 09 55 95 01 75 08 15 00 25 3c b1 02 06 00 ff 15 00 26 ff 00 85 1e 09 01 75 08 95 80 b1 02 85 1f 09 01 75 08 96 3f 01 b1 02 c0',
                         info=(0x3, 0x2793, 0x0001))


class TestIrmtouch_23c9_5666(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test irmtouch_23c9_5666',
                         rdesc='05 0d 09 04 a1 01 85 0a 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 15 00 26 ff 7f 75 10 09 30 81 02 09 31 81 02 05 0d 09 48 09 49 95 02 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 15 00 26 ff 7f 75 10 09 30 81 02 09 31 81 02 05 0d 09 48 09 49 95 02 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 15 00 26 ff 7f 75 10 09 30 81 02 09 31 81 02 05 0d 09 48 09 49 95 02 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 15 00 26 ff 7f 75 10 09 30 81 02 09 31 81 02 05 0d 09 48 09 49 95 02 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 15 00 26 ff 7f 75 10 09 30 81 02 09 31 81 02 05 0d 09 48 09 49 95 02 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 15 00 26 ff 7f 75 10 09 30 81 02 09 31 81 02 05 0d 09 48 09 49 95 02 81 02 c0 05 0d 09 54 95 01 75 08 81 02 09 55 25 06 b1 02 c0 09 0e a1 01 85 0c 09 23 a1 02 09 52 15 00 25 06 75 08 95 01 b1 02 c0 c0',
                         info=(0x3, 0x23c9, 0x5666))


class TestIrtouch_6615_0070(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test irtouch_6615_0070',
                         rdesc='05 01 09 02 a1 01 85 10 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 95 02 75 01 81 02 95 06 81 03 05 01 09 30 09 31 15 00 26 ff 7f 75 10 95 02 81 02 c0 c0 05 0d 09 04 a1 01 85 30 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 09 51 75 08 95 01 81 02 05 01 09 30 26 ff 7f 55 0f 65 11 35 00 46 51 02 75 10 95 01 81 02 09 31 35 00 46 73 01 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 09 51 75 08 95 01 81 02 05 01 09 30 26 ff 7f 55 0f 65 11 35 00 46 51 02 75 10 95 01 81 02 09 31 35 00 46 73 01 81 02 c0 05 0d 09 54 15 00 26 02 00 75 08 95 01 81 02 85 03 09 55 15 00 26 ff 00 75 08 95 01 b1 02 c0 05 0d 09 0e a1 01 85 02 09 52 09 53 15 00 26 ff 00 75 08 95 02 b1 02 c0 05 0d 09 02 a1 01 85 20 09 20 a1 00 09 42 15 00 25 01 75 01 95 01 81 02 95 07 81 03 05 01 09 30 26 ff 7f 55 0f 65 11 35 00 46 51 02 75 10 95 01 81 02 09 31 35 00 46 73 01 81 02 85 01 06 00 ff 09 01 75 08 95 01 b1 02 c0 c0',
                         info=(0x3, 0x6615, 0x0070))


class TestLG_043e_9aa1(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test lg_043e_9aa1',
                         rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 98 12 26 80 07 81 02 09 31 46 78 0a 26 38 04 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 98 12 26 80 07 81 02 46 78 0a 26 38 04 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 98 12 26 80 07 81 02 46 78 0a 26 38 04 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 98 12 26 80 07 81 02 46 78 0a 26 38 04 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 98 12 26 80 07 81 02 46 78 0a 26 38 04 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 98 12 26 80 07 81 02 46 78 0a 26 38 04 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 98 12 26 80 07 81 02 46 78 0a 26 38 04 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 98 12 26 80 07 81 02 46 78 0a 26 38 04 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 98 12 26 80 07 81 02 46 78 0a 26 38 04 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 98 12 26 80 07 81 02 46 78 0a 26 38 04 09 31 81 02 c0 05 0d 09 54 95 01 75 08 15 00 25 0a 81 02 25 0a 09 55 b1 02 c0 09 0e a1 01 85 03 09 22 a1 00 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0 05 01 09 02 a1 01 85 04 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 75 01 95 02 81 02 95 06 81 03 05 01 09 30 75 10 95 01 15 00 26 7f 07 81 02 09 31 26 37 04 81 02 c0 c0 06 00 ff 09 01 a1 01 85 05 15 00 26 ff 00 75 08 95 19 09 01 b1 02 c0 05 14 09 2b a1 02 85 07 09 2b 15 00 25 0a 75 08 95 40 b1 02 09 4b 15 00 25 0a 75 08 95 02 91 02 c0 05 14 09 2c a1 02 85 08 09 2b 15 00 25 0a 75 08 95 05 81 02 09 4b 15 00 25 0a 75 08 95 47 91 02 c0',
                         info=(0x3, 0x043e, 0x9aa1))


class TestLG_043e_9aa3(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test lg_043e_9aa3',
                         rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 98 12 26 80 07 81 02 09 31 46 78 0a 26 38 04 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 98 12 26 80 07 81 02 46 78 0a 26 38 04 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 98 12 26 80 07 81 02 46 78 0a 26 38 04 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 98 12 26 80 07 81 02 46 78 0a 26 38 04 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 98 12 26 80 07 81 02 46 78 0a 26 38 04 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 98 12 26 80 07 81 02 46 78 0a 26 38 04 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 98 12 26 80 07 81 02 46 78 0a 26 38 04 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 98 12 26 80 07 81 02 46 78 0a 26 38 04 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 98 12 26 80 07 81 02 46 78 0a 26 38 04 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 98 12 26 80 07 81 02 46 78 0a 26 38 04 09 31 81 02 c0 05 0d 09 54 95 01 75 08 15 00 25 0a 81 02 25 0a 09 55 b1 02 c0 09 0e a1 01 85 03 09 22 a1 00 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0 05 01 09 02 a1 01 85 04 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 75 01 95 02 81 02 95 06 81 03 05 01 09 30 75 10 95 01 15 00 26 7f 07 81 02 09 31 26 37 04 81 02 c0 c0 06 00 ff 09 01 a1 01 85 05 15 00 26 ff 00 75 08 95 19 09 01 b1 02 c0 05 14 09 2b a1 02 85 07 09 2b 15 00 25 0a 75 08 95 40 b1 02 09 4b 15 00 25 0a 75 08 95 02 91 02 c0 05 14 09 2c a1 02 85 08 09 2b 15 00 25 0a 75 08 95 05 81 02 09 4b 15 00 25 0a 75 08 95 47 91 02 c0',
                         info=(0x3, 0x043e, 0x9aa3))


class TestLG_1fd2_0064(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test lg_1fd2_0064',
                         rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 a1 00 05 01 26 80 07 75 10 55 0e 65 33 09 30 35 00 46 53 07 81 02 26 38 04 46 20 04 09 31 81 02 45 00 c0 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 a1 00 05 01 26 80 07 75 10 55 0e 65 33 09 30 35 00 46 53 07 81 02 26 38 04 46 20 04 09 31 81 02 45 00 c0 c0 05 0d 09 54 95 01 75 08 81 02 85 08 09 55 95 01 25 02 b1 02 c0 09 0e a1 01 85 07 09 23 a1 02 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0 05 01 09 02 a1 01 85 03 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 75 01 95 02 81 02 95 06 81 03 05 01 09 30 09 31 75 10 95 02 15 00 26 ff 7f 81 02 c0 c0',
                         info=(0x3, 0x1fd2, 0x0064))


class TestNexio_1870_0100(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test nexio_1870_0100',
                         rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0e 65 11 09 30 35 00 46 1e 19 81 02 26 ff 3f 09 31 35 00 46 be 0f 81 02 26 ff 3f c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0e 65 11 09 30 35 00 46 1e 19 81 02 26 ff 3f 09 31 35 00 46 be 0f 81 02 26 ff 3f c0 05 0d 09 54 95 01 75 08 25 02 81 02 85 02 09 55 25 02 b1 02 c0 09 0e a1 01 85 03 09 23 a1 02 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0 05 01 09 02 a1 01 09 01 a1 00 85 04 05 09 95 03 75 01 19 01 29 03 15 00 25 01 81 02 95 01 75 05 81 01 05 01 75 10 95 02 09 30 09 31 15 00 26 ff 7f 81 02 c0 c0 05 0d 09 02 a1 01 85 05 09 20 a1 00 09 42 09 32 15 00 25 01 75 01 95 02 81 02 95 0e 81 03 05 01 26 ff 3f 75 10 95 01 55 0e 65 11 09 30 35 00 46 1e 19 81 02 26 ff 3f 09 31 35 00 46 be 0f 81 02 26 ff 3f c0 c0 06 00 ff 09 01 a1 01 85 06 19 01 29 40 15 00 26 ff 00 75 08 95 40 81 00 19 01 29 40 91 00 c0',
                         info=(0x3, 0x1870, 0x0100))


class TestNexio_1870_010d(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test nexio_1870_010d',
                         rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0d 65 00 09 30 35 00 46 00 00 81 02 26 ff 3f 09 31 35 00 46 00 00 81 02 26 ff 3f 05 0d 09 48 35 00 26 ff 3f 81 02 09 49 35 00 26 ff 3f 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0d 65 00 09 30 35 00 46 00 00 81 02 26 ff 3f 09 31 35 00 46 00 00 81 02 26 ff 3f 05 0d 09 48 35 00 26 ff 3f 81 02 09 49 35 00 26 ff 3f 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0d 65 00 09 30 35 00 46 00 00 81 02 26 ff 3f 09 31 35 00 46 00 00 81 02 26 ff 3f 05 0d 09 48 35 00 26 ff 3f 81 02 09 49 35 00 26 ff 3f 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0d 65 00 09 30 35 00 46 00 00 81 02 26 ff 3f 09 31 35 00 46 00 00 81 02 26 ff 3f 05 0d 09 48 35 00 26 ff 3f 81 02 09 49 35 00 26 ff 3f 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0d 65 00 09 30 35 00 46 00 00 81 02 26 ff 3f 09 31 35 00 46 00 00 81 02 26 ff 3f 05 0d 09 48 35 00 26 ff 3f 81 02 09 49 35 00 26 ff 3f 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0d 65 00 09 30 35 00 46 00 00 81 02 26 ff 3f 09 31 35 00 46 00 00 81 02 26 ff 3f 05 0d 09 48 35 00 26 ff 3f 81 02 09 49 35 00 26 ff 3f 81 02 c0 05 0d 09 54 95 01 75 08 25 02 81 02 85 02 09 55 25 06 b1 02 c0 09 0e a1 01 85 03 09 23 a1 02 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0 05 01 09 02 a1 01 09 01 a1 00 85 04 05 09 95 03 75 01 19 01 29 03 15 00 25 01 81 02 95 01 75 05 81 01 05 01 75 10 95 02 09 30 09 31 15 00 26 ff 7f 81 02 c0 c0 05 0d 09 02 a1 01 85 05 09 20 a1 00 09 42 09 32 15 00 25 01 75 01 95 02 81 02 95 0e 81 03 05 01 26 ff 3f 75 10 95 01 55 0e 65 11 09 30 35 00 46 1e 19 81 02 26 ff 3f 09 31 35 00 46 be 0f 81 02 26 ff 3f c0 c0 06 00 ff 09 01 a1 01 85 06 19 01 29 40 15 00 26 ff 00 75 08 95 3e 81 00 19 01 29 40 91 00 c0',
                         info=(0x3, 0x1870, 0x010d))


class TestNexio_1870_0119(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test nexio_1870_0119',
                         rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0d 65 00 09 30 35 00 46 00 00 81 02 26 ff 3f 09 31 35 00 46 00 00 81 02 26 ff 3f 05 0d 09 48 35 00 26 ff 3f 81 02 09 49 35 00 26 ff 3f 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0d 65 00 09 30 35 00 46 00 00 81 02 26 ff 3f 09 31 35 00 46 00 00 81 02 26 ff 3f 05 0d 09 48 35 00 26 ff 3f 81 02 09 49 35 00 26 ff 3f 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0d 65 00 09 30 35 00 46 00 00 81 02 26 ff 3f 09 31 35 00 46 00 00 81 02 26 ff 3f 05 0d 09 48 35 00 26 ff 3f 81 02 09 49 35 00 26 ff 3f 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0d 65 00 09 30 35 00 46 00 00 81 02 26 ff 3f 09 31 35 00 46 00 00 81 02 26 ff 3f 05 0d 09 48 35 00 26 ff 3f 81 02 09 49 35 00 26 ff 3f 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0d 65 00 09 30 35 00 46 00 00 81 02 26 ff 3f 09 31 35 00 46 00 00 81 02 26 ff 3f 05 0d 09 48 35 00 26 ff 3f 81 02 09 49 35 00 26 ff 3f 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0d 65 00 09 30 35 00 46 00 00 81 02 26 ff 3f 09 31 35 00 46 00 00 81 02 26 ff 3f 05 0d 09 48 35 00 26 ff 3f 81 02 09 49 35 00 26 ff 3f 81 02 c0 05 0d 09 54 95 01 75 08 25 02 81 02 85 02 09 55 25 06 b1 02 c0 09 0e a1 01 85 03 09 23 a1 02 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0 05 01 09 02 a1 01 09 01 a1 00 85 04 05 09 95 03 75 01 19 01 29 03 15 00 25 01 81 02 95 01 75 05 81 01 05 01 75 10 95 02 09 30 09 31 15 00 26 ff 7f 81 02 c0 c0 05 0d 09 02 a1 01 85 05 09 20 a1 00 09 42 09 32 15 00 25 01 75 01 95 02 81 02 95 0e 81 03 05 01 26 ff 3f 75 10 95 01 55 0e 65 11 09 30 35 00 46 1e 19 81 02 26 ff 3f 09 31 35 00 46 be 0f 81 02 26 ff 3f c0 c0 06 00 ff 09 01 a1 01 85 06 19 01 29 40 15 00 26 ff 00 75 08 95 3e 81 00 19 01 29 40 91 00 c0',
                         info=(0x3, 0x1870, 0x0119))


class TestPqlabs_1ef1_0001(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test pqlabs_1ef1_0001',
                         rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0e 65 11 09 30 35 00 46 1e 19 81 02 26 ff 3f 09 31 35 00 46 be 0f 81 02 26 ff 3f c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0e 65 11 09 30 35 00 46 1e 19 81 02 26 ff 3f 09 31 35 00 46 be 0f 81 02 26 ff 3f c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0e 65 11 09 30 35 00 46 1e 19 81 02 26 ff 3f 09 31 35 00 46 be 0f 81 02 26 ff 3f c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0e 65 11 09 30 35 00 46 1e 19 81 02 26 ff 3f 09 31 35 00 46 be 0f 81 02 26 ff 3f c0 05 0d 09 54 95 01 75 08 25 02 81 02 85 02 09 55 25 02 b1 02 c0 09 0e a1 01 85 03 09 23 a1 02 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0 05 01 09 02 a1 01 09 01 a1 00 85 04 05 09 95 03 75 01 19 01 29 03 15 00 25 01 81 02 95 01 75 05 81 01 05 01 75 10 95 02 09 30 09 31 15 00 26 ff 3f 81 02 c0 c0 05 8c 09 07 a1 01 85 11 09 02 15 00 26 ff 00 75 08 95 3f 81 02 85 10 09 10 91 02 c0',
                         info=(0x3, 0x1ef1, 0x0001))


class TestQuanta_0408_3000(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test quanta_0408_3000',
                         rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 e3 13 26 7f 07 81 02 09 31 46 2f 0b 26 37 04 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 e3 13 26 7f 07 81 02 46 2f 0b 26 37 04 09 31 81 02 c0 05 0d 09 54 15 00 26 ff 00 95 01 75 08 81 02 09 55 25 02 95 01 85 02 b1 02 06 00 ff 09 01 26 ff 00 75 08 95 2f 85 03 b1 02 09 01 96 ff 03 85 04 b1 02 09 01 95 0b 85 05 b1 02 09 01 96 ff 03 85 06 b1 02 c0',
                         info=(0x3, 0x0408, 0x3000))


class TestQuanta_0408_3008_1(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test quanta_0408_3008_1',
                         rdesc='05 01 09 02 a1 01 85 0d 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 95 02 75 01 81 02 95 01 75 06 81 03 05 01 55 0e 65 11 75 10 95 01 35 00 46 4c 11 26 7f 07 09 30 81 22 46 bb 09 26 37 04 09 31 81 22 95 08 75 08 81 03 c0 c0 05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 4c 11 26 7f 07 81 02 09 31 46 bb 09 26 37 04 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 4c 11 26 7f 07 81 02 46 bb 09 26 37 04 09 31 81 02 c0 05 0d 09 54 15 00 26 ff 00 95 01 75 08 81 02 09 55 25 02 95 01 85 02 b1 02 c0 05 0d 09 0e a1 01 06 00 ff 09 01 26 ff 00 75 08 95 47 85 03 b1 02 09 01 96 ff 03 85 04 b1 02 09 01 95 0b 85 05 b1 02 09 01 96 ff 03 85 06 b1 02 09 01 95 0f 85 07 b1 02 09 01 96 ff 03 85 08 b1 02 09 01 96 ff 03 85 09 b1 02 09 01 95 3f 85 0a b1 02 09 01 96 ff 03 85 0b b1 02 09 01 96 c3 03 85 0e b1 02 09 01 96 ff 03 85 0f b1 02 09 01 96 83 03 85 10 b1 02 09 01 96 93 00 85 11 b1 02 09 01 96 ff 03 85 12 b1 02 05 0d 09 23 a1 02 09 52 09 53 15 00 25 0a 75 08 95 02 85 0c b1 02 c0 c0',
                         info=(0x3, 0x0408, 0x3008))


class TestQuanta_0408_3008(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test quanta_0408_3008',
                         rdesc='05 01 09 02 a1 01 85 0d 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 95 02 75 01 81 02 95 01 75 06 81 03 05 01 55 0e 65 11 75 10 95 01 35 00 46 98 12 26 7f 07 09 30 81 22 46 78 0a 26 37 04 09 31 81 22 c0 c0 05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 98 12 26 7f 07 81 02 09 31 46 78 0a 26 37 04 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 98 12 26 7f 07 81 02 46 78 0a 26 37 04 09 31 81 02 c0 05 0d 09 54 15 00 26 ff 00 95 01 75 08 81 02 09 55 25 02 95 01 85 02 b1 02 c0 05 0d 09 0e a1 01 06 00 ff 09 01 26 ff 00 75 08 95 47 85 03 b1 02 09 01 96 ff 03 85 04 b1 02 09 01 95 0b 85 05 b1 02 09 01 96 ff 03 85 06 b1 02 09 01 95 0f 85 07 b1 02 09 01 96 ff 03 85 08 b1 02 09 01 96 ff 03 85 09 b1 02 09 01 95 3f 85 0a b1 02 09 01 96 ff 03 85 0b b1 02 09 01 96 c3 03 85 0e b1 02 09 01 96 ff 03 85 0f b1 02 09 01 96 83 03 85 10 b1 02 09 01 96 93 00 85 11 b1 02 09 01 96 ff 03 85 12 b1 02 05 0d 09 23 a1 02 09 52 09 53 15 00 25 0a 75 08 95 02 85 0c b1 02 c0 c0',
                         info=(0x3, 0x0408, 0x3008))


class TestRafi_05bd_0107(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test rafi_05bd_0107',
                         rdesc='05 0d 09 04 a1 01 85 01 09 22 65 00 55 00 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 25 09 95 01 81 02 05 01 46 9c 01 26 ff 03 35 00 75 10 09 30 81 02 46 e7 00 26 ff 03 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 25 09 95 01 81 02 05 01 46 9c 01 26 ff 03 35 00 75 10 09 30 81 02 46 e7 00 26 ff 03 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 25 09 95 01 81 02 05 01 46 9c 01 26 ff 03 35 00 75 10 09 30 81 02 46 e7 00 26 ff 03 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 25 09 95 01 81 02 05 01 46 9c 01 26 ff 03 35 00 75 10 09 30 81 02 46 e7 00 26 ff 03 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 25 09 95 01 81 02 05 01 46 9c 01 26 ff 03 35 00 75 10 09 30 81 02 46 e7 00 26 ff 03 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 25 09 95 01 81 02 05 01 46 9c 01 26 ff 03 35 00 75 10 09 30 81 02 46 e7 00 26 ff 03 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 25 09 95 01 81 02 05 01 46 9c 01 26 ff 03 35 00 75 10 09 30 81 02 46 e7 00 26 ff 03 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 25 09 95 01 81 02 05 01 46 9c 01 26 ff 03 35 00 75 10 09 30 81 02 46 e7 00 26 ff 03 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 25 09 95 01 81 02 05 01 46 9c 01 26 ff 03 35 00 75 10 09 30 81 02 46 e7 00 26 ff 03 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 25 09 95 01 81 02 05 01 46 9c 01 26 ff 03 35 00 75 10 09 30 81 02 46 e7 00 26 ff 03 09 31 81 02 c0 05 0d 09 54 95 01 75 08 15 00 25 09 81 02 05 0d 85 02 95 01 75 08 09 55 25 0a b1 02 c0 09 0e a1 01 85 03 09 23 a1 02 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0 05 01 09 02 a1 01 09 01 a1 00 85 05 05 09 19 01 29 02 15 00 25 01 95 02 75 01 81 02 95 06 81 03 05 01 65 11 55 0f 09 30 26 ff 03 35 00 46 9c 01 75 10 95 01 81 02 09 31 26 ff 03 35 00 46 e7 00 81 02 c0 c0',
                         info=(0x3, 0x05bd, 0x0107))


class TestRndplus_2512_5003(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test rndplus_2512_5003',
                         rdesc='05 0d 09 04 a1 01 85 02 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 00 65 00 09 30 35 00 46 00 00 81 02 09 31 46 00 00 81 02 05 0d 09 48 09 49 75 10 95 02 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 00 65 00 09 30 35 00 46 00 00 81 02 09 31 46 00 00 81 02 05 0d 09 48 09 49 75 10 95 02 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 00 65 00 09 30 35 00 46 00 00 81 02 09 31 46 00 00 81 02 05 0d 09 48 09 49 75 10 95 02 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 00 65 00 09 30 35 00 46 00 00 81 02 09 31 46 00 00 81 02 05 0d 09 48 09 49 75 10 95 02 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 00 65 00 09 30 35 00 46 00 00 81 02 09 31 46 00 00 81 02 05 0d 09 48 09 49 75 10 95 02 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 00 65 00 09 30 35 00 46 00 00 81 02 09 31 46 00 00 81 02 05 0d 09 48 09 49 75 10 95 02 81 02 c0 05 0d 09 54 95 01 75 08 15 00 25 08 81 02 85 08 09 55 b1 02 c0 09 0e a1 01 85 07 09 23 a1 02 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0 05 01 09 02 a1 01 85 03 09 01 a1 00 05 09 19 01 29 03 15 00 25 01 95 03 75 01 81 02 95 01 75 05 81 01 05 01 09 30 09 31 16 00 00 26 ff 3f 36 00 00 46 ff 3f 66 00 00 75 10 95 02 81 62 c0 c0',
                         info=(0x3, 0x2512, 0x5003))


class TestRndplus_2512_5004(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test rndplus_2512_5004',
                         rdesc='05 0d 09 04 a1 01 85 04 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 00 65 00 09 30 35 00 46 00 00 81 02 09 31 46 00 00 81 02 05 0d 09 48 09 49 75 10 95 02 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 00 65 00 09 30 35 00 46 00 00 81 02 09 31 46 00 00 81 02 05 0d 09 48 09 49 75 10 95 02 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 00 65 00 09 30 35 00 46 00 00 81 02 09 31 46 00 00 81 02 05 0d 09 48 09 49 75 10 95 02 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 00 65 00 09 30 35 00 46 00 00 81 02 09 31 46 00 00 81 02 05 0d 09 48 09 49 75 10 95 02 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 00 65 00 09 30 35 00 46 00 00 81 02 09 31 46 00 00 81 02 05 0d 09 48 09 49 75 10 95 02 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 00 65 00 09 30 35 00 46 00 00 81 02 09 31 46 00 00 81 02 05 0d 09 48 09 49 75 10 95 02 81 02 c0 05 0d 09 54 95 01 75 08 15 00 25 08 81 02 85 05 09 55 b1 02 c0 09 0e a1 01 85 06 09 23 a1 02 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0 05 01 09 02 a1 01 85 03 09 01 a1 00 05 09 19 01 29 03 15 00 25 01 95 03 75 01 81 02 95 01 75 05 81 01 05 01 09 30 09 31 16 00 00 26 ff 3f 36 00 00 46 ff 3f 66 00 00 75 10 95 02 81 62 c0 c0 06 00 ff 09 01 a1 01 85 01 09 01 15 00 26 ff 00 75 08 95 3f 82 00 01 85 02 09 01 15 00 26 ff 00 75 08 95 3f 92 00 01 c0',
                         info=(0x3, 0x2512, 0x5004))


class TestStantum_1f87_0002(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test stantum_1f87_0002',
                         rdesc='05 0d 09 04 a1 01 85 03 05 0d 09 54 95 01 75 08 81 02 06 00 ff 75 02 09 01 81 01 75 0e 09 02 81 02 05 0d 09 22 a1 02 05 01 16 00 00 26 ff 07 75 0b 55 00 65 00 09 30 81 02 05 0d 25 1f 75 05 09 48 81 02 05 01 16 00 00 26 ff 07 75 0b 55 00 65 00 09 31 81 02 05 0d 25 1f 75 05 09 49 81 02 75 08 09 51 95 01 81 02 09 30 75 05 81 02 09 42 15 00 25 01 75 01 95 01 81 02 09 47 81 02 09 32 81 02 c0 a1 02 05 01 16 00 00 26 ff 07 75 0b 55 00 65 00 09 30 81 02 05 0d 25 1f 75 05 09 48 81 02 05 01 16 00 00 26 ff 07 75 0b 55 00 65 00 09 31 81 02 05 0d 25 1f 75 05 09 49 81 02 75 08 09 51 95 01 81 02 09 30 75 05 81 02 09 42 15 00 25 01 75 01 95 01 81 02 09 47 81 02 09 32 81 02 c0 a1 02 05 01 16 00 00 26 ff 07 75 0b 55 00 65 00 09 30 81 02 05 0d 25 1f 75 05 09 48 81 02 05 01 16 00 00 26 ff 07 75 0b 55 00 65 00 09 31 81 02 05 0d 25 1f 75 05 09 49 81 02 75 08 09 51 95 01 81 02 09 30 75 05 81 02 09 42 15 00 25 01 75 01 95 01 81 02 09 47 81 02 09 32 81 02 c0 a1 02 05 01 16 00 00 26 ff 07 75 0b 55 00 65 00 09 30 81 02 05 0d 25 1f 75 05 09 48 81 02 05 01 16 00 00 26 ff 07 75 0b 55 00 65 00 09 31 81 02 05 0d 25 1f 75 05 09 49 81 02 75 08 09 51 95 01 81 02 09 30 75 05 81 02 09 42 15 00 25 01 75 01 95 01 81 02 09 47 81 02 09 32 81 02 c0 a1 02 05 01 16 00 00 26 ff 07 75 0b 55 00 65 00 09 30 81 02 05 0d 25 1f 75 05 09 48 81 02 05 01 16 00 00 26 ff 07 75 0b 55 00 65 00 09 31 81 02 05 0d 25 1f 75 05 09 49 81 02 75 08 09 51 95 01 81 02 09 30 75 05 81 02 09 42 15 00 25 01 75 01 95 01 81 02 09 47 81 02 09 32 81 02 c0 a1 02 05 01 16 00 00 26 ff 07 75 0b 55 00 65 00 09 30 81 02 05 0d 25 1f 75 05 09 48 81 02 05 01 16 00 00 26 ff 07 75 0b 55 00 65 00 09 31 81 02 05 0d 25 1f 75 05 09 49 81 02 75 08 09 51 95 01 81 02 09 30 75 05 81 02 09 42 15 00 25 01 75 01 95 01 81 02 09 47 81 02 09 32 81 02 c0 a1 02 05 01 16 00 00 26 ff 07 75 0b 55 00 65 00 09 30 81 02 05 0d 25 1f 75 05 09 48 81 02 05 01 16 00 00 26 ff 07 75 0b 55 00 65 00 09 31 81 02 05 0d 25 1f 75 05 09 49 81 02 75 08 09 51 95 01 81 02 09 30 75 05 81 02 09 42 15 00 25 01 75 01 95 01 81 02 09 47 81 02 09 32 81 02 c0 a1 02 05 01 16 00 00 26 ff 07 75 0b 55 00 65 00 09 30 81 02 05 0d 25 1f 75 05 09 48 81 02 05 01 16 00 00 26 ff 07 75 0b 55 00 65 00 09 31 81 02 05 0d 25 1f 75 05 09 49 81 02 75 08 09 51 95 01 81 02 09 30 75 05 81 02 09 42 15 00 25 01 75 01 95 01 81 02 09 47 81 02 09 32 81 02 c0 a1 02 05 01 16 00 00 26 ff 07 75 0b 55 00 65 00 09 30 81 02 05 0d 25 1f 75 05 09 48 81 02 05 01 16 00 00 26 ff 07 75 0b 55 00 65 00 09 31 81 02 05 0d 25 1f 75 05 09 49 81 02 75 08 09 51 95 01 81 02 09 30 75 05 81 02 09 42 15 00 25 01 75 01 95 01 81 02 09 47 81 02 09 32 81 02 c0 a1 02 05 01 16 00 00 26 ff 07 75 0b 55 00 65 00 09 30 81 02 05 0d 25 1f 75 05 09 48 81 02 05 01 16 00 00 26 ff 07 75 0b 55 00 65 00 09 31 81 02 05 0d 25 1f 75 05 09 49 81 02 75 08 09 51 95 01 81 02 09 30 75 05 81 02 09 42 15 00 25 01 75 01 95 01 81 02 09 47 81 02 09 32 81 02 c0 85 08 05 0d 09 55 95 01 75 08 25 0a b1 02 c0',
                         info=(0x3, 0x1f87, 0x0002))


class TestTpv_25aa_8883(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test tpv_25aa_8883',
                         rdesc='05 01 09 02 a1 01 85 0d 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 95 02 75 01 81 02 05 0d 09 32 95 01 75 01 81 02 95 01 75 05 81 03 05 01 55 0e 65 11 75 10 95 01 35 00 46 98 12 26 7f 07 09 30 81 22 46 78 0a 26 37 04 09 31 81 22 35 00 45 00 15 81 25 7f 75 08 95 01 09 38 81 06 09 00 75 08 95 07 81 03 c0 c0 05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 98 12 26 7f 07 81 02 09 31 46 78 0a 26 37 04 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 75 10 55 0e 65 11 09 30 35 00 46 98 12 26 7f 07 81 02 46 78 0a 26 37 04 09 31 81 02 c0 05 0d 09 54 15 00 26 ff 00 95 01 75 08 81 02 09 55 25 02 95 01 85 02 b1 02 c0 05 0d 09 0e a1 01 06 00 ff 09 01 26 ff 00 75 08 95 47 85 03 b1 02 09 01 96 ff 03 85 04 b1 02 09 01 95 0b 85 05 b1 02 09 01 96 ff 03 85 06 b1 02 09 01 95 0f 85 07 b1 02 09 01 96 ff 03 85 08 b1 02 09 01 96 ff 03 85 09 b1 02 09 01 95 3f 85 0a b1 02 09 01 96 ff 03 85 0b b1 02 09 01 96 c3 03 85 0e b1 02 09 01 96 ff 03 85 0f b1 02 09 01 96 83 03 85 10 b1 02 09 01 96 93 00 85 11 b1 02 09 01 96 ff 03 85 12 b1 02 05 0d 09 23 a1 02 09 52 09 53 15 00 25 0a 75 08 95 02 85 0c b1 02 c0 c0',
                         info=(0x3, 0x25aa, 0x8883))


class TestUnitec_227d_0103(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test unitec_227d_0103',
                         rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 09 51 75 08 95 01 81 02 05 01 35 00 55 0e 65 33 75 10 95 01 09 30 16 00 00 26 ff 4f 36 00 00 46 6c 03 81 02 09 31 16 00 00 26 ff 3b 36 00 00 46 ed 01 81 02 26 00 00 46 00 00 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 09 51 75 08 95 01 81 02 05 01 35 00 55 0e 65 33 75 10 95 01 09 30 16 00 00 26 ff 4f 36 00 00 46 6c 03 81 02 09 31 16 00 00 26 ff 3b 36 00 00 46 ed 01 81 02 26 00 00 46 00 00 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 09 51 75 08 95 01 81 02 05 01 35 00 55 0e 65 33 75 10 95 01 09 30 16 00 00 26 ff 4f 36 00 00 46 6c 03 81 02 09 31 16 00 00 26 ff 3b 36 00 00 46 ed 01 81 02 26 00 00 46 00 00 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 09 51 75 08 95 01 81 02 05 01 35 00 55 0e 65 33 75 10 95 01 09 30 16 00 00 26 ff 4f 36 00 00 46 6c 03 81 02 09 31 16 00 00 26 ff 3b 36 00 00 46 ed 01 81 02 26 00 00 46 00 00 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 09 51 75 08 95 01 81 02 05 01 35 00 55 0e 65 33 75 10 95 01 09 30 16 00 00 26 ff 4f 36 00 00 46 6c 03 81 02 09 31 16 00 00 26 ff 3b 36 00 00 46 ed 01 81 02 26 00 00 46 00 00 c0 05 0d 09 54 75 08 95 01 81 02 05 0d 85 03 09 55 25 05 75 08 95 01 b1 02 c0 05 0d 09 0e a1 01 85 04 09 53 15 00 25 05 75 08 95 01 b1 02 c0',
                         info=(0x3, 0x227d, 0x0103))


class TestZytronic_14c8_0005(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test zytronic_14c8_0005',
                         rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 95 01 81 02 95 06 81 01 05 01 26 00 10 75 10 95 01 65 00 09 30 81 02 09 31 46 00 10 81 02 05 0d 09 51 26 ff 00 75 08 95 01 81 02 c0 85 02 09 55 15 00 25 08 75 08 95 01 b1 02 c0 05 0d 09 0e a1 01 85 03 a1 02 09 23 09 52 09 53 15 00 25 08 75 08 95 02 b1 02 c0 c0 05 01 09 02 a1 01 09 01 a1 00 85 04 05 09 19 01 29 02 15 00 25 01 95 02 75 01 81 02 95 01 75 06 81 01 05 01 09 30 09 31 15 00 26 00 10 35 00 46 00 10 65 00 75 10 95 02 81 62 c0 c0 06 00 ff 09 01 a1 01 85 05 09 00 15 00 26 ff 00 75 08 95 3f b1 02 c0 06 00 ff 09 01 a1 01 85 06 09 00 15 00 26 ff 00 75 08 95 3f 81 02 c0',
                         info=(0x3, 0x14c8, 0x0005))


class TestZytronic_14c8_0006(BaseTest.TestMultitouch):
    def _create_device(self):
        return Digitizer('uhid test zytronic_14c8_0006',
                         rdesc='05 0d 09 04 a1 01 85 01 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 00 10 75 10 09 30 81 02 09 31 81 02 05 0d c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 00 10 75 10 09 30 81 02 09 31 81 02 05 0d c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 00 10 75 10 09 30 81 02 09 31 81 02 05 0d c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 00 10 75 10 09 30 81 02 09 31 81 02 05 0d c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 00 10 75 10 09 30 81 02 09 31 81 02 05 0d c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 00 10 75 10 09 30 81 02 09 31 81 02 05 0d c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 00 10 75 10 09 30 81 02 09 31 81 02 05 0d c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 00 10 75 10 09 30 81 02 09 31 81 02 05 0d c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 00 10 75 10 09 30 81 02 09 31 81 02 05 0d c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 00 10 75 10 09 30 81 02 09 31 81 02 05 0d c0 05 0d 09 54 95 01 75 08 15 00 25 3c 81 02 05 0d 85 02 09 55 95 01 75 08 15 00 25 3c b1 02 c0 09 0e a1 01 85 03 09 23 a1 02 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0 05 01 09 02 a1 01 09 01 a1 00 85 04 05 09 19 01 29 02 15 00 25 01 95 02 75 01 81 02 95 01 75 06 81 01 05 01 09 30 09 31 15 00 26 00 10 35 00 46 00 10 65 00 75 10 95 02 81 62 c0 c0 06 00 ff 09 01 a1 01 85 05 09 00 15 00 26 ff 00 75 08 95 3f b1 02 c0 06 00 ff 09 01 a1 01 85 06 09 00 15 00 26 ff 00 75 08 95 3f 81 02 c0',
                         info=(0x3, 0x14c8, 0x0006))


################################################################################
#
# Windows 8 compatible devices
#
################################################################################

class TestMinWin8TSParallelTriple(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return MinWin8TSParallel(3)


class TestMinWin8TSParallel(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return MinWin8TSParallel(10)


class TestMinWin8TSHybrid(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return MinWin8TSHybrid()


class TestElanXPS9360(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test ElanXPS9360', rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 a4 26 20 0d 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 50 07 46 a6 00 09 31 81 02 b4 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 a4 26 20 0d 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 50 07 46 a6 00 09 31 81 02 b4 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 a4 26 20 0d 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 50 07 46 a6 00 09 31 81 02 b4 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 a4 26 20 0d 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 50 07 46 a6 00 09 31 81 02 b4 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 a4 26 20 0d 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 50 07 46 a6 00 09 31 81 02 b4 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 a4 26 20 0d 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 50 07 46 a6 00 09 31 81 02 b4 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 a4 26 20 0d 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 50 07 46 a6 00 09 31 81 02 b4 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 a4 26 20 0d 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 50 07 46 a6 00 09 31 81 02 b4 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 a4 26 20 0d 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 50 07 46 a6 00 09 31 81 02 b4 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 a4 26 20 0d 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 50 07 46 a6 00 09 31 81 02 b4 c0 05 0d 09 56 55 00 65 00 27 ff ff ff 7f 95 01 75 20 81 02 09 54 25 7f 95 01 75 08 81 02 85 0a 09 55 25 0a b1 02 85 44 06 00 ff 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 06 ff 01 09 01 a1 01 85 02 15 00 26 ff 00 75 08 95 40 09 00 81 02 c0 06 00 ff 09 01 a1 01 85 03 75 08 95 1f 09 01 91 02 c0 06 01 ff 09 01 a1 01 85 04 15 00 26 ff 00 75 08 95 13 09 00 81 02 c0')


class TestTouchpadXPS9360(BaseTest.TestPTP):
    def _create_device(self):
        return PTP('uhid test TouchpadXPS9360', max_contacts=5, rdesc='05 01 09 02 a1 01 85 02 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 75 01 95 02 81 02 95 06 81 01 05 01 09 30 09 31 15 81 25 7f 75 08 95 02 81 06 c0 c0 05 0d 09 05 a1 01 85 03 05 0d 09 22 a1 02 15 00 25 01 09 47 09 42 95 02 75 01 81 02 95 01 75 03 25 05 09 51 81 02 75 01 95 03 81 03 05 01 15 00 26 c0 04 75 10 55 0e 65 11 09 30 35 00 46 f5 03 95 01 81 02 46 36 02 26 a8 02 09 31 81 02 c0 05 0d 09 22 a1 02 15 00 25 01 09 47 09 42 95 02 75 01 81 02 95 01 75 03 25 05 09 51 81 02 75 01 95 03 81 03 05 01 15 00 26 c0 04 75 10 55 0e 65 11 09 30 35 00 46 f5 03 95 01 81 02 46 36 02 26 a8 02 09 31 81 02 c0 05 0d 09 22 a1 02 15 00 25 01 09 47 09 42 95 02 75 01 81 02 95 01 75 03 25 05 09 51 81 02 75 01 95 03 81 03 05 01 15 00 26 c0 04 75 10 55 0e 65 11 09 30 35 00 46 f5 03 95 01 81 02 46 36 02 26 a8 02 09 31 81 02 c0 05 0d 09 22 a1 02 15 00 25 01 09 47 09 42 95 02 75 01 81 02 95 01 75 03 25 05 09 51 81 02 75 01 95 03 81 03 05 01 15 00 26 c0 04 75 10 55 0e 65 11 09 30 35 00 46 f5 03 95 01 81 02 46 36 02 26 a8 02 09 31 81 02 c0 05 0d 09 22 a1 02 15 00 25 01 09 47 09 42 95 02 75 01 81 02 95 01 75 03 25 05 09 51 81 02 75 01 95 03 81 03 05 01 15 00 26 c0 04 75 10 55 0e 65 11 09 30 35 00 46 f5 03 95 01 81 02 46 36 02 26 a8 02 09 31 81 02 c0 05 0d 55 0c 66 01 10 47 ff ff 00 00 27 ff ff 00 00 75 10 95 01 09 56 81 02 09 54 25 7f 95 01 75 08 81 02 05 09 09 01 25 01 75 01 95 01 81 02 95 07 81 03 05 0d 85 08 09 55 09 59 75 04 95 02 25 0f b1 02 85 0d 09 60 75 01 95 01 15 00 25 01 b1 02 95 07 b1 03 85 07 06 00 ff 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 05 0d 09 0e a1 01 85 04 09 22 a1 02 09 52 15 00 25 0a 75 08 95 01 b1 02 c0 09 22 a1 00 85 06 09 57 09 58 75 01 95 02 25 01 b1 02 95 06 b1 03 c0 c0 06 00 ff 09 01 a1 01 85 09 09 02 15 00 26 ff 00 75 08 95 14 91 02 85 0a 09 03 15 00 26 ff 00 75 08 95 14 91 02 85 0b 09 04 15 00 26 ff 00 75 08 95 3d 81 02 85 0c 09 05 15 00 26 ff 00 75 08 95 3d 81 02 85 0f 09 06 15 00 26 ff 00 75 08 95 03 b1 02 85 0e 09 07 15 00 26 ff 00 75 08 95 01 b1 02 c0')


class Test3m_0596_051c(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test 3m_0596_051c', rdesc='05 01 09 01 a1 01 85 01 09 01 a1 00 05 09 09 01 95 01 75 01 15 00 25 01 81 02 95 07 75 01 81 03 95 01 75 08 81 03 05 01 09 30 09 31 15 00 26 ff 7f 35 00 46 ff 7f 95 02 75 10 81 02 c0 a1 02 15 00 26 ff 00 09 01 95 39 75 08 81 03 c0 c0 05 0d 09 0e a1 01 85 11 09 23 a1 02 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0 09 04 a1 01 85 13 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 81 03 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 d1 12 81 02 09 31 46 b2 0b 81 02 06 00 ff 75 10 95 02 09 01 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 81 03 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 d1 12 81 02 09 31 46 b2 0b 81 02 06 00 ff 75 10 95 02 09 01 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 81 03 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 d1 12 81 02 09 31 46 b2 0b 81 02 06 00 ff 75 10 95 02 09 01 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 81 03 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 d1 12 81 02 09 31 46 b2 0b 81 02 06 00 ff 75 10 95 02 09 01 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 81 03 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 d1 12 81 02 09 31 46 b2 0b 81 02 06 00 ff 75 10 95 02 09 01 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 81 03 09 47 81 02 95 05 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 d1 12 81 02 09 31 46 b2 0b 81 02 06 00 ff 75 10 95 02 09 01 81 02 c0 05 0d 09 54 95 01 75 08 15 00 25 14 81 02 05 0d 55 0c 66 01 10 35 00 47 ff ff 00 00 27 ff ff 00 00 75 10 95 01 09 56 81 02 05 0d 09 55 85 12 15 00 25 14 75 08 95 01 b1 02 85 44 06 00 ff 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 06 00 ff 15 00 26 ff 00 85 03 09 01 75 08 95 07 b1 02 85 04 09 01 75 08 95 17 b1 02 85 05 09 01 75 08 95 47 b1 02 85 06 09 01 75 08 95 07 b1 02 85 73 09 01 75 08 95 07 b1 02 85 08 09 01 75 08 95 07 b1 02 85 09 09 01 75 08 95 3f b1 02 85 0f 09 01 75 08 96 07 02 b1 02 c0')


class Testadvanced_silicon_04e8_2084(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test advanced_silicon_04e8_2084', rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 c0 14 81 02 46 ae 0b 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 c0 14 81 02 46 ae 0b 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 c0 14 81 02 46 ae 0b 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 c0 14 81 02 46 ae 0b 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 c0 14 81 02 46 ae 0b 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 c0 14 81 02 46 ae 0b 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 c0 14 81 02 46 ae 0b 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 c0 14 81 02 46 ae 0b 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 c0 14 81 02 46 ae 0b 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 c0 14 81 02 46 ae 0b 09 31 81 02 45 00 c0 05 0d 15 00 27 ff ff 00 00 75 10 95 01 09 56 81 02 25 0a 75 08 09 54 81 02 85 44 09 55 b1 02 85 44 06 00 ff 09 c5 26 ff 00 96 00 01 b1 02 85 f0 09 01 95 04 b1 02 85 f2 09 03 b1 02 09 04 b1 02 09 05 b1 02 95 01 09 06 b1 02 09 07 b1 02 85 f1 09 02 95 07 91 02 85 f3 09 08 95 3d b1 02 c0')


class Testadvanced_silicon_2149_2306(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test advanced_silicon_2149_2306', rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 f6 13 81 02 46 40 0b 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 f6 13 81 02 46 40 0b 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 f6 13 81 02 46 40 0b 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 f6 13 81 02 46 40 0b 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 f6 13 81 02 46 40 0b 09 31 81 02 45 00 c0 05 0d 15 00 27 ff ff 00 00 75 10 95 01 09 56 81 02 25 0a 75 08 09 54 81 02 85 44 09 55 b1 02 85 44 06 00 ff 09 c5 26 ff 00 96 00 01 b1 02 85 f0 09 01 95 04 81 02 85 f2 09 03 b1 02 09 04 b1 02 09 05 b1 02 95 01 09 06 b1 02 09 07 b1 02 85 f1 09 02 95 07 91 02 85 f3 09 08 95 3d b1 02 c0')


class Testadvanced_silicon_2149_230a(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test advanced_silicon_2149_230a', rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 f6 13 81 02 46 40 0b 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 f6 13 81 02 46 40 0b 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 f6 13 81 02 46 40 0b 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 f6 13 81 02 46 40 0b 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 f6 13 81 02 46 40 0b 09 31 81 02 45 00 c0 05 0d 15 00 27 ff ff 00 00 75 10 95 01 09 56 81 02 25 0a 75 08 09 54 81 02 85 44 09 55 b1 02 85 44 06 00 ff 09 c5 26 ff 00 96 00 01 b1 02 85 f0 09 01 95 04 81 02 85 f2 09 03 b1 02 09 04 b1 02 09 05 b1 02 95 01 09 06 b1 02 09 07 b1 02 85 f1 09 02 95 07 91 02 85 f3 09 08 95 3d b1 02 c0')


class Testadvanced_silicon_2149_231c(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test advanced_silicon_2149_231c', rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 e2 13 81 02 46 32 0b 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 e2 13 81 02 46 32 0b 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 e2 13 81 02 46 32 0b 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 e2 13 81 02 46 32 0b 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 e2 13 81 02 46 32 0b 09 31 81 02 45 00 c0 05 0d 15 00 27 ff ff 00 00 75 10 95 01 09 56 81 02 25 0a 75 08 09 54 81 02 85 44 09 55 b1 02 85 44 06 00 ff 09 c5 26 ff 00 96 00 01 b1 02 85 f0 09 01 95 04 b1 02 85 f2 09 03 b1 02 09 04 b1 02 09 05 b1 02 95 01 09 06 b1 02 09 07 b1 02 85 f1 09 02 95 07 91 02 85 f3 09 08 95 3d b1 02 c0')


class Testadvanced_silicon_2149_2703(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test advanced_silicon_2149_2703', rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 66 17 81 02 46 34 0d 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 66 17 81 02 46 34 0d 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 66 17 81 02 46 34 0d 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 66 17 81 02 46 34 0d 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 66 17 81 02 46 34 0d 09 31 81 02 45 00 c0 05 0d 15 00 27 ff ff 00 00 75 10 95 01 09 56 81 02 25 0a 75 08 09 54 81 02 85 44 09 55 b1 02 85 44 06 00 ff 09 c5 26 ff 00 96 00 01 b1 02 85 f0 09 01 95 04 81 02 85 f2 09 03 b1 02 09 04 b1 02 09 05 b1 02 95 01 09 06 b1 02 09 07 b1 02 85 f1 09 02 95 07 91 02 85 f3 09 08 95 3d b1 02 c0')


class Testadvanced_silicon_2149_270b(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test advanced_silicon_2149_270b', rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 52 17 81 02 46 20 0d 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 52 17 81 02 46 20 0d 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 52 17 81 02 46 20 0d 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 52 17 81 02 46 20 0d 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 52 17 81 02 46 20 0d 09 31 81 02 45 00 c0 05 0d 15 00 27 ff ff 00 00 75 10 95 01 09 56 81 02 25 0a 75 08 09 54 81 02 85 44 09 55 b1 02 85 44 06 00 ff 09 c5 26 ff 00 96 00 01 b1 02 85 f0 09 01 95 04 b1 02 85 f2 09 03 b1 02 09 04 b1 02 09 05 b1 02 95 01 09 06 b1 02 09 07 b1 02 85 f1 09 02 95 07 91 02 85 f3 09 08 95 3d b1 02 c0')


class Testadvanced_silicon_2575_0204(BaseTest.TestWin8Multitouch):
    """ found on the Dell Canvas 27"""
    def _create_device(self):
        return Digitizer('uhid test advanced_silicon_2575_0204', rdesc='05 0d 09 04 a1 01 85 01 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 25 7f 09 51 75 07 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 4f 17 81 02 46 1d 0d 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 25 7f 09 51 75 07 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 4f 17 81 02 46 1d 0d 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 25 7f 09 51 75 07 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 4f 17 81 02 46 1d 0d 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 25 7f 09 51 75 07 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 4f 17 81 02 46 1d 0d 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 25 7f 09 51 75 07 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 4f 17 81 02 46 1d 0d 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 25 7f 09 51 75 07 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 4f 17 81 02 46 1d 0d 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 25 7f 09 51 75 07 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 4f 17 81 02 46 1d 0d 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 25 7f 09 51 75 07 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 4f 17 81 02 46 1d 0d 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 25 7f 09 51 75 07 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 4f 17 81 02 46 1d 0d 09 31 81 02 45 00 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 25 7f 09 51 75 07 95 01 81 02 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 4f 17 81 02 46 1d 0d 09 31 81 02 45 00 c0 05 0d 15 00 27 ff ff 00 00 75 10 95 01 09 56 81 02 25 0a 75 08 09 54 81 02 85 42 09 55 25 0a b1 02 85 44 06 00 ff 09 c5 26 ff 00 96 00 01 b1 02 c0 05 01 09 0e a1 01 85 05 05 01 09 08 a1 00 09 30 55 0e 65 11 15 00 26 ff 7f 35 00 46 4f 17 75 10 95 01 81 42 09 31 46 1d 0d 81 42 06 00 ff 09 01 75 20 81 03 05 01 09 37 55 00 65 14 16 98 fe 26 68 01 36 98 fe 46 68 01 75 0f 81 06 05 09 09 01 65 00 15 00 25 01 35 00 45 00 75 01 81 02 05 0d 09 42 81 02 09 51 75 07 25 7f 81 02 05 0d 09 48 55 0e 65 11 15 00 26 ff 7f 35 00 46 ff 7f 75 10 81 02 09 49 81 02 09 3f 55 00 65 14 15 00 26 67 01 35 00 46 67 01 81 0a c0 65 00 35 00 45 00 05 0d 15 00 27 ff ff 00 00 75 10 95 01 09 56 81 02 25 05 75 08 09 54 81 02 85 47 09 55 25 05 b1 02 c0 06 00 ff 09 04 a1 01 85 f0 09 01 75 08 95 04 b1 02 85 f2 09 03 b1 02 09 04 b1 02 09 05 b1 02 85 c0 09 01 95 03 b1 02 85 c2 09 01 95 0f b1 02 85 c4 09 01 95 3e b1 02 85 c5 09 01 95 7e b1 02 85 c6 09 01 95 fe b1 02 85 c8 09 01 96 fe 03 b1 02 85 0a 09 01 95 3f b1 02 c0')


class Testadvanced_silicon_2619_5610(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test advanced_silicon_2619_5610', rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 a1 00 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 f9 15 81 02 46 73 0c 09 31 81 02 45 00 c0 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 a1 00 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 f9 15 81 02 46 73 0c 09 31 81 02 45 00 c0 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 a1 00 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 f9 15 81 02 46 73 0c 09 31 81 02 45 00 c0 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 a1 00 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 f9 15 81 02 46 73 0c 09 31 81 02 45 00 c0 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 a1 00 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 f9 15 81 02 46 73 0c 09 31 81 02 45 00 c0 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 a1 00 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 f9 15 81 02 46 73 0c 09 31 81 02 45 00 c0 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 a1 00 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 f9 15 81 02 46 73 0c 09 31 81 02 45 00 c0 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 a1 00 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 f9 15 81 02 46 73 0c 09 31 81 02 45 00 c0 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 a1 00 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 f9 15 81 02 46 73 0c 09 31 81 02 45 00 c0 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 02 81 03 09 51 25 1f 75 05 95 01 81 02 a1 00 05 01 26 ff 7f 75 10 55 0e 65 11 09 30 35 00 46 f9 15 81 02 46 73 0c 09 31 81 02 45 00 c0 c0 05 0d 15 00 27 ff ff 00 00 75 10 95 01 09 56 81 02 25 0a 75 08 09 54 81 02 85 44 09 55 b1 02 85 44 06 00 ff 09 c5 26 ff 00 96 00 01 b1 02 85 f0 09 01 95 04 81 02 85 f2 09 03 b1 02 09 04 b1 02 09 05 b1 02 95 01 09 06 b1 02 09 07 b1 02 85 f1 09 02 95 07 91 02 c0')


class Testatmel_03eb_8409(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test atmel_03eb_8409', rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 95 01 81 03 25 1f 75 05 09 51 81 02 05 01 55 0e 65 11 35 00 75 10 95 02 46 c8 0a 26 6f 08 09 30 81 02 35 00 35 00 46 18 06 26 77 0f 09 31 81 02 35 00 35 00 05 0d 95 01 75 08 15 00 26 ff 00 46 ff 00 09 48 81 02 09 49 81 02 c0 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 95 01 81 03 25 1f 75 05 09 51 81 02 05 01 55 0e 65 11 35 00 75 10 95 02 46 c8 0a 26 6f 08 09 30 81 02 35 00 35 00 46 18 06 26 77 0f 09 31 81 02 35 00 35 00 05 0d 95 01 75 08 15 00 26 ff 00 46 ff 00 09 48 81 02 09 49 81 02 c0 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 95 01 81 03 25 1f 75 05 09 51 81 02 05 01 55 0e 65 11 35 00 75 10 95 02 46 c8 0a 26 6f 08 09 30 81 02 35 00 35 00 46 18 06 26 77 0f 09 31 81 02 35 00 35 00 05 0d 95 01 75 08 15 00 26 ff 00 46 ff 00 09 48 81 02 09 49 81 02 c0 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 95 01 81 03 25 1f 75 05 09 51 81 02 05 01 55 0e 65 11 35 00 75 10 95 02 46 c8 0a 26 6f 08 09 30 81 02 35 00 35 00 46 18 06 26 77 0f 09 31 81 02 35 00 35 00 05 0d 95 01 75 08 15 00 26 ff 00 46 ff 00 09 48 81 02 09 49 81 02 c0 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 95 01 81 03 25 1f 75 05 09 51 81 02 05 01 55 0e 65 11 35 00 75 10 95 02 46 c8 0a 26 6f 08 09 30 81 02 35 00 35 00 46 18 06 26 77 0f 09 31 81 02 35 00 35 00 05 0d 95 01 75 08 15 00 26 ff 00 46 ff 00 09 48 81 02 09 49 81 02 c0 05 0d 27 ff ff 00 00 75 10 95 01 09 56 81 02 15 00 25 1f 75 05 09 54 95 01 81 02 75 03 25 01 95 01 81 03 75 08 85 02 09 55 25 10 b1 02 06 00 ff 85 05 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 05 0d 09 00 a1 01 85 03 09 20 a1 00 15 00 25 01 75 01 95 01 09 42 81 02 09 44 81 02 09 45 81 02 81 03 09 32 81 02 95 03 81 03 05 01 55 0e 65 11 35 00 75 10 95 02 46 c8 0a 26 6f 08 09 30 81 02 46 18 06 26 77 0f 09 31 81 02 05 0d 09 30 15 01 26 ff 00 75 08 95 01 81 02 c0 c0')


class Testatmel_03eb_840b(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test atmel_03eb_840b', rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 95 01 81 03 25 1f 75 05 09 51 81 02 05 01 55 0e 65 11 35 00 75 10 95 01 46 00 0a 26 ff 0f 09 30 81 02 09 00 81 03 46 a0 05 26 ff 0f 09 31 81 02 09 00 81 03 05 0d 95 01 75 08 15 00 26 ff 00 46 ff 00 09 00 81 03 09 00 81 03 c0 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 95 01 81 03 25 1f 75 05 09 51 81 02 05 01 55 0e 65 11 35 00 75 10 95 01 46 00 0a 26 ff 0f 09 30 81 02 09 00 81 03 46 a0 05 26 ff 0f 09 31 81 02 09 00 81 03 05 0d 95 01 75 08 15 00 26 ff 00 46 ff 00 09 00 81 03 09 00 81 03 c0 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 95 01 81 03 25 1f 75 05 09 51 81 02 05 01 55 0e 65 11 35 00 75 10 95 01 46 00 0a 26 ff 0f 09 30 81 02 09 00 81 03 46 a0 05 26 ff 0f 09 31 81 02 09 00 81 03 05 0d 95 01 75 08 15 00 26 ff 00 46 ff 00 09 00 81 03 09 00 81 03 c0 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 95 01 81 03 25 1f 75 05 09 51 81 02 05 01 55 0e 65 11 35 00 75 10 95 01 46 00 0a 26 ff 0f 09 30 81 02 09 00 81 03 46 a0 05 26 ff 0f 09 31 81 02 09 00 81 03 05 0d 95 01 75 08 15 00 26 ff 00 46 ff 00 09 00 81 03 09 00 81 03 c0 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 95 01 81 03 25 1f 75 05 09 51 81 02 05 01 55 0e 65 11 35 00 75 10 95 01 46 00 0a 26 ff 0f 09 30 81 02 09 00 81 03 46 a0 05 26 ff 0f 09 31 81 02 09 00 81 03 05 0d 95 01 75 08 15 00 26 ff 00 46 ff 00 09 00 81 03 09 00 81 03 c0 05 0d 27 ff ff 00 00 75 10 95 01 09 56 81 02 15 00 25 1f 75 05 09 54 95 01 81 02 75 03 25 01 95 01 81 03 75 08 85 02 09 55 25 10 b1 02 06 00 ff 85 05 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 05 0d 09 02 a1 01 85 03 09 20 a1 00 15 00 25 01 75 01 95 01 09 42 81 02 09 44 81 02 09 45 81 02 81 03 09 32 81 02 95 03 81 03 05 01 55 0e 65 11 35 00 75 10 95 02 46 00 0a 26 ff 0f 09 30 81 02 46 a0 05 26 ff 0f 09 31 81 02 05 0d 09 30 15 01 26 ff 00 75 08 95 01 81 02 c0 c0')


class Testdell_044e_1220(BaseTest.TestPTP):
    def _create_device(self):
        return PTP('uhid test dell_044e_1220', type='pressurepad', rdesc='05 01 09 02 a1 01 85 01 09 01 a1 00 05 09 19 01 29 03 15 00 25 01 75 01 95 03 81 02 95 05 81 01 05 01 09 30 09 31 15 81 25 7f 75 08 95 02 81 06 09 38 95 01 81 06 05 0c 0a 38 02 81 06 c0 c0 05 0d 09 05 a1 01 85 08 09 22 a1 02 15 00 25 01 09 47 09 42 95 02 75 01 81 02 95 01 75 03 25 05 09 51 81 02 75 01 95 03 81 03 05 01 15 00 26 af 04 75 10 55 0e 65 11 09 30 35 00 46 e8 03 95 01 81 02 26 7b 02 46 12 02 09 31 81 02 c0 55 0c 66 01 10 47 ff ff 00 00 27 ff ff 00 00 75 10 95 01 05 0d 09 56 81 02 09 54 25 05 95 01 75 08 81 02 05 09 19 01 29 03 25 01 75 01 95 03 81 02 95 05 81 03 05 0d 85 09 09 55 75 08 95 01 25 05 b1 02 06 00 ff 85 0a 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 06 01 ff 09 01 a1 01 85 03 09 01 15 00 26 ff 00 95 1b 81 02 85 04 09 02 95 50 81 02 85 05 09 03 95 07 b1 02 85 06 09 04 81 02 c0 06 02 ff 09 01 a1 01 85 07 09 02 95 86 75 08 b1 02 c0 05 0d 09 0e a1 01 85 0b 09 22 a1 02 09 52 15 00 25 0a 75 08 95 01 b1 02 c0 09 22 a1 00 85 0c 09 57 09 58 75 01 95 02 25 01 b1 02 95 06 b1 03 c0 c0')


class Testdell_06cb_75db(BaseTest.TestPTP):
    def _create_device(self):
        return PTP('uhid test dell_06cb_75db', max_contacts=3, rdesc='05 01 09 02 a1 01 85 02 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 75 01 95 02 81 02 95 06 81 01 05 01 09 30 09 31 15 81 25 7f 75 08 95 02 81 06 c0 c0 05 0d 09 05 a1 01 85 03 09 22 a1 02 15 00 25 01 09 47 09 42 95 02 75 01 81 02 95 01 75 03 25 05 09 51 81 02 75 01 95 03 81 03 05 01 15 00 26 c8 04 75 10 55 0e 65 11 09 30 35 00 46 fb 03 95 01 81 02 46 6c 02 26 e8 02 09 31 81 02 c0 05 0d 09 22 a1 02 15 00 25 01 09 47 09 42 95 02 75 01 81 02 95 01 75 03 25 05 09 51 81 02 75 01 95 03 81 03 05 01 15 00 26 c8 04 75 10 55 0e 65 11 09 30 35 00 46 fb 03 95 01 81 02 46 6c 02 26 e8 02 09 31 81 02 c0 05 0d 09 22 a1 02 15 00 25 01 09 47 09 42 95 02 75 01 81 02 95 01 75 03 25 05 09 51 81 02 75 01 95 03 81 03 05 01 15 00 26 c8 04 75 10 55 0e 65 11 09 30 35 00 46 fb 03 95 01 81 02 46 6c 02 26 e8 02 09 31 81 02 05 0d c0 55 0c 66 01 10 47 ff ff 00 00 27 ff ff 00 00 75 10 95 01 09 56 81 02 09 54 25 7f 95 01 75 08 81 02 05 09 09 01 25 01 75 01 95 01 81 02 95 07 81 03 05 0d 85 08 09 55 09 59 75 04 95 02 25 0f b1 02 85 0d 09 60 75 01 95 01 15 00 25 01 b1 02 95 07 b1 03 85 07 06 00 ff 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 05 0d 09 0e a1 01 85 04 09 22 a1 02 09 52 15 00 25 0a 75 08 95 01 b1 02 c0 09 22 a1 00 85 06 09 57 09 58 75 01 95 02 25 01 b1 02 95 06 b1 03 c0 c0 06 00 ff 09 01 a1 01 85 09 09 02 15 00 26 ff 00 75 08 95 14 91 02 85 0a 09 03 15 00 26 ff 00 75 08 95 14 91 02 85 0b 09 04 15 00 26 ff 00 75 08 95 1a 81 02 85 0c 09 05 15 00 26 ff 00 75 08 95 1a 81 02 85 0f 09 06 15 00 26 ff 00 75 08 95 01 b1 02 85 0e 09 07 15 00 26 ff 00 75 08 95 01 b1 02 c0')


class Testegalax_capacitive_0eef_790a(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test egalax_capacitive_0eef_790a', max_contacts=10, rdesc='05 0d 09 04 a1 01 85 06 05 0d 09 54 75 08 15 00 25 0c 95 01 81 02 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 07 81 03 75 08 09 51 95 01 15 00 25 20 81 02 05 01 26 ff 0f 75 10 55 0e 65 11 09 30 35 00 46 13 0c 81 02 46 cb 06 09 31 81 02 75 08 95 02 81 03 81 03 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 07 81 03 75 08 09 51 95 01 15 00 25 20 81 02 05 01 26 ff 0f 75 10 55 0e 65 11 09 30 35 00 46 13 0c 81 02 46 cb 06 09 31 81 02 75 08 95 02 81 03 81 03 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 07 81 03 75 08 09 51 95 01 15 00 25 20 81 02 05 01 26 ff 0f 75 10 55 0e 65 11 09 30 35 00 46 13 0c 81 02 46 cb 06 09 31 81 02 75 08 95 02 81 03 81 03 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 07 81 03 75 08 09 51 95 01 15 00 25 20 81 02 05 01 26 ff 0f 75 10 55 0e 65 11 09 30 35 00 46 13 0c 81 02 46 cb 06 09 31 81 02 75 08 95 02 81 03 81 03 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 07 81 03 75 08 09 51 95 01 15 00 25 20 81 02 05 01 26 ff 0f 75 10 55 0e 65 11 09 30 35 00 46 13 0c 81 02 46 cb 06 09 31 81 02 75 08 95 02 81 03 81 03 c0 05 0d 17 00 00 00 00 27 ff ff ff 7f 75 20 95 01 55 00 65 00 09 56 81 02 09 55 09 53 75 08 95 02 26 ff 00 b1 02 06 00 ff 09 c5 85 07 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 05 01 09 01 a1 01 85 01 09 01 a1 02 05 09 19 01 29 02 15 00 25 01 95 02 75 01 81 02 95 01 75 06 81 01 05 01 09 30 09 31 16 00 00 26 ff 0f 36 00 00 46 ff 0f 66 00 00 75 10 95 02 81 02 c0 c0 06 00 ff 09 01 a1 01 09 01 15 00 26 ff 00 85 03 75 08 95 3f 81 02 06 00 ff 09 01 15 00 26 ff 00 75 08 95 3f 91 02 c0 05 0d 09 0e a1 01 85 05 09 23 a1 02 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0')


class Testelan_04f3_000a(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test elan_04f3_000a', rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0e 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 00 08 46 a6 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0e 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 00 08 46 a6 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0e 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 00 08 46 a6 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0e 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 00 08 46 a6 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0e 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 00 08 46 a6 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0e 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 00 08 46 a6 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0e 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 00 08 46 a6 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0e 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 00 08 46 a6 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0e 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 00 08 46 a6 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0e 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 00 08 46 a6 00 09 31 81 02 c0 05 0d 09 56 55 00 65 00 27 ff ff ff 7f 95 01 75 20 81 02 09 54 25 7f 95 01 75 08 81 02 85 0a 09 55 25 0a b1 02 85 44 06 00 ff 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 06 ff 01 09 01 a1 01 85 02 15 00 26 ff 00 75 08 95 40 09 00 81 02 c0 06 00 ff 09 01 a1 01 85 03 75 08 95 1f 09 01 91 02 c0 06 01 ff 09 01 a1 01 85 04 15 00 26 ff 00 75 08 95 13 09 00 81 02 c0')


class Testelan_04f3_000c(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test elan_04f3_000c', rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 40 0e 75 10 55 0f 65 11 09 30 35 00 46 01 01 95 02 81 02 26 00 08 46 91 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 40 0e 75 10 55 0f 65 11 09 30 35 00 46 01 01 95 02 81 02 26 00 08 46 91 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 40 0e 75 10 55 0f 65 11 09 30 35 00 46 01 01 95 02 81 02 26 00 08 46 91 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 40 0e 75 10 55 0f 65 11 09 30 35 00 46 01 01 95 02 81 02 26 00 08 46 91 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 40 0e 75 10 55 0f 65 11 09 30 35 00 46 01 01 95 02 81 02 26 00 08 46 91 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 40 0e 75 10 55 0f 65 11 09 30 35 00 46 01 01 95 02 81 02 26 00 08 46 91 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 40 0e 75 10 55 0f 65 11 09 30 35 00 46 01 01 95 02 81 02 26 00 08 46 91 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 40 0e 75 10 55 0f 65 11 09 30 35 00 46 01 01 95 02 81 02 26 00 08 46 91 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 40 0e 75 10 55 0f 65 11 09 30 35 00 46 01 01 95 02 81 02 26 00 08 46 91 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 40 0e 75 10 55 0f 65 11 09 30 35 00 46 01 01 95 02 81 02 26 00 08 46 91 00 09 31 81 02 c0 05 0d 09 56 55 00 65 00 27 ff ff ff 7f 95 01 75 20 81 02 09 54 25 7f 95 01 75 08 81 02 85 0a 09 55 25 0a b1 02 85 44 06 00 ff 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 06 ff 01 09 01 a1 01 85 02 15 00 26 ff 00 75 08 95 40 09 00 81 02 c0 06 00 ff 09 01 a1 01 85 03 75 08 95 1f 09 01 91 02 c0 06 01 ff 09 01 a1 01 85 04 15 00 26 ff 00 75 08 95 13 09 00 81 02 c0')


class Testelan_04f3_010c(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test elan_04f3_010c', rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 f0 0c 75 10 55 0f 65 11 09 30 35 00 46 58 01 95 02 81 02 26 50 07 46 c2 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 f0 0c 75 10 55 0f 65 11 09 30 35 00 46 58 01 95 02 81 02 26 50 07 46 c2 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 f0 0c 75 10 55 0f 65 11 09 30 35 00 46 58 01 95 02 81 02 26 50 07 46 c2 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 f0 0c 75 10 55 0f 65 11 09 30 35 00 46 58 01 95 02 81 02 26 50 07 46 c2 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 f0 0c 75 10 55 0f 65 11 09 30 35 00 46 58 01 95 02 81 02 26 50 07 46 c2 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 f0 0c 75 10 55 0f 65 11 09 30 35 00 46 58 01 95 02 81 02 26 50 07 46 c2 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 f0 0c 75 10 55 0f 65 11 09 30 35 00 46 58 01 95 02 81 02 26 50 07 46 c2 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 f0 0c 75 10 55 0f 65 11 09 30 35 00 46 58 01 95 02 81 02 26 50 07 46 c2 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 f0 0c 75 10 55 0f 65 11 09 30 35 00 46 58 01 95 02 81 02 26 50 07 46 c2 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 f0 0c 75 10 55 0f 65 11 09 30 35 00 46 58 01 95 02 81 02 26 50 07 46 c2 00 09 31 81 02 c0 05 0d 09 56 55 00 65 00 27 ff ff ff 7f 95 01 75 20 81 02 09 54 25 7f 95 01 75 08 81 02 85 0a 09 55 25 0a b1 02 85 44 06 00 ff 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 06 ff 01 09 01 a1 01 85 02 15 00 26 ff 00 75 08 95 40 09 00 81 02 c0 06 00 ff 09 01 a1 01 85 03 75 08 95 1f 09 01 91 02 c0 06 01 ff 09 01 a1 01 85 04 15 00 26 ff 00 75 08 95 13 09 00 81 02 c0')


class Testelan_04f3_0125(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test elan_04f3_0125', rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 f0 0c 75 10 55 0f 65 11 09 30 35 00 46 58 01 95 02 81 02 26 50 07 46 c1 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 f0 0c 75 10 55 0f 65 11 09 30 35 00 46 58 01 95 02 81 02 26 50 07 46 c1 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 f0 0c 75 10 55 0f 65 11 09 30 35 00 46 58 01 95 02 81 02 26 50 07 46 c1 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 f0 0c 75 10 55 0f 65 11 09 30 35 00 46 58 01 95 02 81 02 26 50 07 46 c1 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 f0 0c 75 10 55 0f 65 11 09 30 35 00 46 58 01 95 02 81 02 26 50 07 46 c1 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 f0 0c 75 10 55 0f 65 11 09 30 35 00 46 58 01 95 02 81 02 26 50 07 46 c1 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 f0 0c 75 10 55 0f 65 11 09 30 35 00 46 58 01 95 02 81 02 26 50 07 46 c1 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 f0 0c 75 10 55 0f 65 11 09 30 35 00 46 58 01 95 02 81 02 26 50 07 46 c1 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 f0 0c 75 10 55 0f 65 11 09 30 35 00 46 58 01 95 02 81 02 26 50 07 46 c1 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 f0 0c 75 10 55 0f 65 11 09 30 35 00 46 58 01 95 02 81 02 26 50 07 46 c1 00 09 31 81 02 c0 05 0d 09 56 55 00 65 00 27 ff ff ff 7f 95 01 75 20 81 02 09 54 25 7f 95 01 75 08 81 02 85 0a 09 55 25 0a b1 02 85 44 06 00 ff 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 06 ff 01 09 01 a1 01 85 02 15 00 26 ff 00 75 08 95 40 09 00 81 02 c0 06 00 ff 09 01 a1 01 85 03 75 08 95 1f 09 01 91 02 c0 06 01 ff 09 01 a1 01 85 04 15 00 26 ff 00 75 08 95 13 09 00 81 02 c0')


class Testelan_04f3_016f(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test elan_04f3_016f', rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0e 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 40 08 46 a6 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0e 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 40 08 46 a6 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0e 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 40 08 46 a6 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0e 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 40 08 46 a6 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0e 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 40 08 46 a6 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0e 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 40 08 46 a6 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0e 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 40 08 46 a6 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0e 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 40 08 46 a6 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0e 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 40 08 46 a6 00 09 31 81 02 c0 05 0d 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 75 01 81 03 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0e 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 40 08 46 a6 00 09 31 81 02 c0 05 0d 09 56 55 00 65 00 27 ff ff ff 7f 95 01 75 20 81 02 09 54 25 7f 95 01 75 08 81 02 85 0a 09 55 25 0a b1 02 85 44 06 00 ff 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 06 ff 01 09 01 a1 01 85 02 15 00 26 ff 00 75 08 95 40 09 00 81 02 c0 06 00 ff 09 01 a1 01 85 03 75 08 95 1f 09 01 91 02 c0 06 01 ff 09 01 a1 01 85 04 15 00 26 ff 00 75 08 95 13 09 00 81 02 c0')


class Testelan_04f3_0732(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test elan_04f3_0732', rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0b 75 10 55 0f 65 11 09 30 35 00 46 ff 00 95 02 81 02 26 40 07 46 85 00 09 31 81 02 c0 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0b 75 10 55 0f 65 11 09 30 35 00 46 ff 00 95 02 81 02 26 40 07 46 85 00 09 31 81 02 c0 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0b 75 10 55 0f 65 11 09 30 35 00 46 ff 00 95 02 81 02 26 40 07 46 85 00 09 31 81 02 c0 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0b 75 10 55 0f 65 11 09 30 35 00 46 ff 00 95 02 81 02 26 40 07 46 85 00 09 31 81 02 c0 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0b 75 10 55 0f 65 11 09 30 35 00 46 ff 00 95 02 81 02 26 40 07 46 85 00 09 31 81 02 c0 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0b 75 10 55 0f 65 11 09 30 35 00 46 ff 00 95 02 81 02 26 40 07 46 85 00 09 31 81 02 c0 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0b 75 10 55 0f 65 11 09 30 35 00 46 ff 00 95 02 81 02 26 40 07 46 85 00 09 31 81 02 c0 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0b 75 10 55 0f 65 11 09 30 35 00 46 ff 00 95 02 81 02 26 40 07 46 85 00 09 31 81 02 c0 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0b 75 10 55 0f 65 11 09 30 35 00 46 ff 00 95 02 81 02 26 40 07 46 85 00 09 31 81 02 c0 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0b 75 10 55 0f 65 11 09 30 35 00 46 ff 00 95 02 81 02 26 40 07 46 85 00 09 31 81 02 c0 05 0d 09 56 55 00 65 00 27 ff ff 00 00 95 01 75 20 81 02 09 54 25 7f 95 01 75 08 81 02 85 0a 09 55 25 0a b1 02 85 44 06 00 ff 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 06 ff 01 09 01 a1 01 85 02 15 00 25 ff 75 08 95 40 09 00 81 02 c0 06 00 ff 09 01 a1 01 85 03 75 08 95 1f 09 01 91 02 c0')


class Testelan_04f3_200a(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test elan_04f3_200a', rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0e 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 40 08 46 a6 00 09 31 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 75 06 09 51 25 3f 81 02 26 ff 00 75 08 09 48 81 02 09 49 81 02 95 01 05 01 26 c0 0e 75 10 55 0f 65 11 09 30 35 00 46 26 01 95 02 81 02 26 40 08 46 a6 00 09 31 81 02 c0 05 0d 09 56 55 00 65 00 27 ff ff 00 00 95 01 75 20 81 02 09 54 25 7f 95 01 75 08 81 02 85 0a 09 55 25 0a b1 02 85 0e 06 00 ff 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0')


class Testelan_04f3_300b(BaseTest.TestPTP):
    def _create_device(self):
        return PTP('uhid test elan_04f3_300b', max_contacts=3, rdesc='05 01 09 02 a1 01 85 01 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 75 01 95 02 81 02 95 06 81 03 05 01 09 30 09 31 09 38 15 81 25 7f 75 08 95 03 81 06 05 0c 0a 38 02 95 01 81 06 75 08 95 03 81 03 c0 06 00 ff 85 0d 09 c5 15 00 26 ff 00 75 08 95 04 b1 02 85 0c 09 c6 96 76 02 75 08 b1 02 85 0b 09 c7 95 42 75 08 b1 02 09 01 85 5d 95 1f 75 08 81 06 c0 05 0d 09 05 a1 01 85 04 09 22 a1 02 15 00 25 01 09 47 09 42 95 02 75 01 81 02 95 01 75 02 25 02 09 51 81 02 75 01 95 04 81 03 05 01 15 00 26 a7 0c 75 10 55 0e 65 13 09 30 35 00 46 9d 01 95 01 81 02 46 25 01 26 2b 09 26 2b 09 09 31 81 02 05 0d 15 00 25 64 95 03 c0 55 0c 66 01 10 47 ff ff 00 00 27 ff ff 00 00 75 10 95 01 09 56 81 02 09 54 25 7f 95 01 75 08 81 02 05 09 09 01 25 01 75 01 95 01 81 02 95 07 81 03 05 0d 85 02 09 55 09 59 75 04 95 02 25 0f b1 02 85 07 09 60 75 01 95 01 15 00 25 01 b1 02 95 0f b1 03 06 00 ff 06 00 ff 85 06 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 05 0d 09 0e a1 01 85 03 09 22 a1 00 09 52 15 00 25 0a 75 08 95 02 b1 02 c0 09 22 a1 00 85 05 09 57 09 58 15 00 75 01 95 02 25 03 b1 02 95 0e b1 03 c0 c0')


class Testilitek_222a_0015(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test ilitek_222a_0015', rdesc='05 0d 09 04 a1 01 85 04 09 22 a1 02 05 0d 95 01 75 06 09 51 15 00 25 3f 81 02 09 42 25 01 75 01 95 01 81 02 75 01 95 01 81 03 05 01 75 10 55 0e 65 11 09 30 26 c2 16 35 00 46 b3 08 81 42 09 31 26 c2 0c 46 e4 04 81 42 c0 05 0d 09 22 a1 02 05 0d 95 01 75 06 09 51 15 00 25 3f 81 02 09 42 25 01 75 01 95 01 81 02 75 01 95 01 81 03 05 01 75 10 55 0e 65 11 09 30 26 c2 16 35 00 46 b3 08 81 42 09 31 26 c2 0c 46 e4 04 81 42 c0 05 0d 09 22 a1 02 05 0d 95 01 75 06 09 51 15 00 25 3f 81 02 09 42 25 01 75 01 95 01 81 02 75 01 95 01 81 03 05 01 75 10 55 0e 65 11 09 30 26 c2 16 35 00 46 b3 08 81 42 09 31 26 c2 0c 46 e4 04 81 42 c0 05 0d 09 22 a1 02 05 0d 95 01 75 06 09 51 15 00 25 3f 81 02 09 42 25 01 75 01 95 01 81 02 75 01 95 01 81 03 05 01 75 10 55 0e 65 11 09 30 26 c2 16 35 00 46 b3 08 81 42 09 31 26 c2 0c 46 e4 04 81 42 c0 05 0d 09 22 a1 02 05 0d 95 01 75 06 09 51 15 00 25 3f 81 02 09 42 25 01 75 01 95 01 81 02 75 01 95 01 81 03 05 01 75 10 55 0e 65 11 09 30 26 c2 16 35 00 46 b3 08 81 42 09 31 26 c2 0c 46 e4 04 81 42 c0 05 0d 09 22 a1 02 05 0d 95 01 75 06 09 51 15 00 25 3f 81 02 09 42 25 01 75 01 95 01 81 02 75 01 95 01 81 03 05 01 75 10 55 0e 65 11 09 30 26 c2 16 35 00 46 b3 08 81 42 09 31 26 c2 0c 46 e4 04 81 42 c0 05 0d 09 22 a1 02 05 0d 95 01 75 06 09 51 15 00 25 3f 81 02 09 42 25 01 75 01 95 01 81 02 75 01 95 01 81 03 05 01 75 10 55 0e 65 11 09 30 26 c2 16 35 00 46 b3 08 81 42 09 31 26 c2 0c 46 e4 04 81 42 c0 05 0d 09 22 a1 02 05 0d 95 01 75 06 09 51 15 00 25 3f 81 02 09 42 25 01 75 01 95 01 81 02 75 01 95 01 81 03 05 01 75 10 55 0e 65 11 09 30 26 c2 16 35 00 46 b3 08 81 42 09 31 26 c2 0c 46 e4 04 81 42 c0 05 0d 09 22 a1 02 05 0d 95 01 75 06 09 51 15 00 25 3f 81 02 09 42 25 01 75 01 95 01 81 02 75 01 95 01 81 03 05 01 75 10 55 0e 65 11 09 30 26 c2 16 35 00 46 b3 08 81 42 09 31 26 c2 0c 46 e4 04 81 42 c0 05 0d 09 22 a1 02 05 0d 95 01 75 06 09 51 15 00 25 3f 81 02 09 42 25 01 75 01 95 01 81 02 75 01 95 01 81 03 05 01 75 10 55 0e 65 11 09 30 26 c2 16 35 00 46 b3 08 81 42 09 31 26 c2 0c 46 e4 04 81 42 c0 05 0d 09 56 55 00 65 00 27 ff ff ff 7f 95 01 75 20 81 02 09 54 25 7f 95 01 75 08 81 02 85 02 09 55 25 0a b1 02 06 00 ff 09 c5 85 06 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 06 00 ff 09 01 a1 01 09 01 85 03 15 00 26 ff 00 75 08 95 3f 81 02 06 00 ff 09 01 15 00 26 ff 00 75 08 95 3f 91 02 c0')


class Testilitek_222a_001c(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test ilitek_222a_001c', rdesc='05 0d 09 04 a1 01 85 04 09 22 a1 02 05 0d 95 01 75 06 09 51 15 00 25 3f 81 02 09 42 25 01 75 01 95 01 81 02 75 01 95 01 81 03 05 01 75 10 55 0e 65 11 09 30 26 74 1d 35 00 46 70 0d 81 42 09 31 26 74 10 46 8f 07 81 42 c0 05 0d 09 22 a1 02 05 0d 95 01 75 06 09 51 15 00 25 3f 81 02 09 42 25 01 75 01 95 01 81 02 75 01 95 01 81 03 05 01 75 10 55 0e 65 11 09 30 26 74 1d 35 00 46 70 0d 81 42 09 31 26 74 10 46 8f 07 81 42 c0 05 0d 09 22 a1 02 05 0d 95 01 75 06 09 51 15 00 25 3f 81 02 09 42 25 01 75 01 95 01 81 02 75 01 95 01 81 03 05 01 75 10 55 0e 65 11 09 30 26 74 1d 35 00 46 70 0d 81 42 09 31 26 74 10 46 8f 07 81 42 c0 05 0d 09 22 a1 02 05 0d 95 01 75 06 09 51 15 00 25 3f 81 02 09 42 25 01 75 01 95 01 81 02 75 01 95 01 81 03 05 01 75 10 55 0e 65 11 09 30 26 74 1d 35 00 46 70 0d 81 42 09 31 26 74 10 46 8f 07 81 42 c0 05 0d 09 22 a1 02 05 0d 95 01 75 06 09 51 15 00 25 3f 81 02 09 42 25 01 75 01 95 01 81 02 75 01 95 01 81 03 05 01 75 10 55 0e 65 11 09 30 26 74 1d 35 00 46 70 0d 81 42 09 31 26 74 10 46 8f 07 81 42 c0 05 0d 09 22 a1 02 05 0d 95 01 75 06 09 51 15 00 25 3f 81 02 09 42 25 01 75 01 95 01 81 02 75 01 95 01 81 03 05 01 75 10 55 0e 65 11 09 30 26 74 1d 35 00 46 70 0d 81 42 09 31 26 74 10 46 8f 07 81 42 c0 05 0d 09 22 a1 02 05 0d 95 01 75 06 09 51 15 00 25 3f 81 02 09 42 25 01 75 01 95 01 81 02 75 01 95 01 81 03 05 01 75 10 55 0e 65 11 09 30 26 74 1d 35 00 46 70 0d 81 42 09 31 26 74 10 46 8f 07 81 42 c0 05 0d 09 22 a1 02 05 0d 95 01 75 06 09 51 15 00 25 3f 81 02 09 42 25 01 75 01 95 01 81 02 75 01 95 01 81 03 05 01 75 10 55 0e 65 11 09 30 26 74 1d 35 00 46 70 0d 81 42 09 31 26 74 10 46 8f 07 81 42 c0 05 0d 09 22 a1 02 05 0d 95 01 75 06 09 51 15 00 25 3f 81 02 09 42 25 01 75 01 95 01 81 02 75 01 95 01 81 03 05 01 75 10 55 0e 65 11 09 30 26 74 1d 35 00 46 70 0d 81 42 09 31 26 74 10 46 8f 07 81 42 c0 05 0d 09 22 a1 02 05 0d 95 01 75 06 09 51 15 00 25 3f 81 02 09 42 25 01 75 01 95 01 81 02 75 01 95 01 81 03 05 01 75 10 55 0e 65 11 09 30 26 74 1d 35 00 46 70 0d 81 42 09 31 26 74 10 46 8f 07 81 42 c0 05 0d 09 56 55 00 65 00 27 ff ff ff 7f 95 01 75 20 81 02 09 54 25 7f 95 01 75 08 81 02 85 02 09 55 25 0a b1 02 06 00 ff 09 c5 85 06 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 06 00 ff 09 01 a1 01 09 01 85 03 15 00 26 ff 00 75 08 95 3f 81 02 06 00 ff 09 01 15 00 26 ff 00 75 08 95 3f 91 02 c0')


class Testn_trig_1b96_0c01(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test n_trig_1b96_0c01', rdesc='75 08 15 00 26 ff 00 06 0b ff 09 0b a1 01 95 0f 09 29 85 29 b1 02 95 1f 09 2a 85 2a b1 02 95 3e 09 2b 85 2b b1 02 95 fe 09 2c 85 2c b1 02 96 fe 01 09 2d 85 2d b1 02 95 02 09 48 85 48 b1 02 95 0f 09 2e 85 2e 81 02 95 1f 09 2f 85 2f 81 02 95 3e 09 30 85 30 81 02 95 fe 09 31 85 31 81 02 96 fe 01 09 32 85 32 81 02 75 08 96 fe 0f 09 35 85 35 81 02 c0 05 0d 09 02 a1 01 85 01 09 20 35 00 a1 00 09 32 09 42 09 44 09 3c 09 45 15 00 25 01 75 01 95 05 81 02 95 03 81 03 05 01 09 30 75 10 95 01 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 b4 05 0d 09 30 26 00 01 81 02 06 00 ff 09 01 81 02 c0 85 0c 06 00 ff 09 0c 75 08 95 06 26 ff 00 b1 02 85 0b 09 0b 95 02 b1 02 85 11 09 11 b1 02 85 15 09 15 95 05 b1 02 85 18 09 18 95 0c b1 02 c0 05 0d 09 04 a1 01 85 03 06 00 ff 09 01 75 10 95 01 15 00 27 ff ff 00 00 81 02 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 54 95 01 75 08 81 02 09 56 75 20 95 01 27 ff ff ff 0f 81 02 85 04 09 55 75 08 95 01 25 0b b1 02 85 0a 06 00 ff 09 03 15 00 b1 02 85 1b 06 00 ff 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 05 01 09 02 a1 01 85 02 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 75 01 95 02 81 02 95 06 81 03 05 01 09 30 09 31 15 81 25 7f 75 08 95 02 81 06 c0 c0')


class Testn_trig_1b96_0c03(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test n_trig_1b96_0c03', rdesc='75 08 15 00 26 ff 00 06 0b ff 09 0b a1 01 95 0f 09 29 85 29 b1 02 95 1f 09 2a 85 2a b1 02 95 3e 09 2b 85 2b b1 02 95 fe 09 2c 85 2c b1 02 96 fe 01 09 2d 85 2d b1 02 95 02 09 48 85 48 b1 02 95 0f 09 2e 85 2e 81 02 95 1f 09 2f 85 2f 81 02 95 3e 09 30 85 30 81 02 95 fe 09 31 85 31 81 02 96 fe 01 09 32 85 32 81 02 75 08 96 fe 0f 09 35 85 35 81 02 c0 05 0d 09 02 a1 01 85 01 09 20 35 00 a1 00 09 32 09 42 09 44 09 3c 09 45 15 00 25 01 75 01 95 05 81 02 95 03 81 03 05 01 09 30 75 10 95 01 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 b4 05 0d 09 30 26 00 01 81 02 06 00 ff 09 01 81 02 c0 85 0c 06 00 ff 09 0c 75 08 95 06 26 ff 00 b1 02 85 0b 09 0b 95 02 b1 02 85 11 09 11 b1 02 85 15 09 15 95 05 b1 02 85 18 09 18 95 0c b1 02 c0 05 0d 09 04 a1 01 85 03 06 00 ff 09 01 75 10 95 01 15 00 27 ff ff 00 00 81 02 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 54 95 01 75 08 81 02 09 56 75 20 95 01 27 ff ff ff 0f 81 02 85 04 09 55 75 08 95 01 25 0b b1 02 85 0a 06 00 ff 09 03 15 00 b1 02 85 1b 06 00 ff 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 05 01 09 02 a1 01 85 02 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 75 01 95 02 81 02 95 06 81 03 05 01 09 30 09 31 15 81 25 7f 75 08 95 02 81 06 c0 c0')


class Testn_trig_1b96_0f00(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test n_trig_1b96_0f00', rdesc='75 08 15 00 26 ff 00 06 0b ff 09 0b a1 01 95 0f 09 29 85 29 b1 02 95 1f 09 2a 85 2a b1 02 95 3e 09 2b 85 2b b1 02 95 fe 09 2c 85 2c b1 02 96 fe 01 09 2d 85 2d b1 02 95 02 09 48 85 48 b1 02 95 0f 09 2e 85 2e 81 02 95 1f 09 2f 85 2f 81 02 95 3e 09 30 85 30 81 02 95 fe 09 31 85 31 81 02 96 fe 01 09 32 85 32 81 02 75 08 96 fe 0f 09 35 85 35 81 02 c0 05 0d 09 02 a1 01 85 01 09 20 35 00 a1 00 09 32 09 42 09 44 09 3c 09 45 15 00 25 01 75 01 95 05 81 02 95 03 81 03 05 01 09 30 75 10 95 01 a4 55 0e 65 11 46 03 0a 26 80 25 81 02 09 31 46 a1 05 26 20 1c 81 02 b4 05 0d 09 30 26 00 01 81 02 06 00 ff 09 01 81 02 c0 85 0c 06 00 ff 09 0c 75 08 95 06 26 ff 00 b1 02 85 0b 09 0b 95 02 b1 02 85 11 09 11 b1 02 85 15 09 15 95 05 b1 02 85 18 09 18 95 0c b1 02 c0 05 0d 09 04 a1 01 85 03 06 00 ff 09 01 75 10 95 01 15 00 27 ff ff 00 00 81 02 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 03 0a 26 80 25 81 02 09 31 46 a1 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 03 0a 26 80 25 81 02 09 31 46 a1 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 54 95 01 75 08 81 02 09 56 75 20 95 01 27 ff ff ff 0f 81 02 85 04 09 55 75 08 95 01 25 0b b1 02 85 0a 06 00 ff 09 03 15 00 b1 02 85 1b 06 00 ff 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 05 01 09 02 a1 01 85 02 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 75 01 95 02 81 02 95 06 81 03 05 01 09 30 09 31 15 81 25 7f 75 08 95 02 81 06 c0 c0')


class Testn_trig_1b96_0f04(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test n_trig_1b96_0f04', rdesc='75 08 15 00 26 ff 00 06 0b ff 09 0b a1 01 95 0f 09 29 85 29 b1 02 95 1f 09 2a 85 2a b1 02 95 3e 09 2b 85 2b b1 02 95 fe 09 2c 85 2c b1 02 96 fe 01 09 2d 85 2d b1 02 95 02 09 48 85 48 b1 02 95 0f 09 2e 85 2e 81 02 95 1f 09 2f 85 2f 81 02 95 3e 09 30 85 30 81 02 95 fe 09 31 85 31 81 02 96 fe 01 09 32 85 32 81 02 75 08 96 fe 0f 09 35 85 35 81 02 c0 05 0d 09 02 a1 01 85 01 09 20 35 00 a1 00 09 32 09 42 09 44 09 3c 09 45 15 00 25 01 75 01 95 05 81 02 95 03 81 03 05 01 09 30 75 10 95 01 a4 55 0e 65 11 46 7f 0b 26 80 25 81 02 09 31 46 78 06 26 20 1c 81 02 b4 05 0d 09 30 26 00 01 81 02 06 00 ff 09 01 81 02 c0 85 0c 06 00 ff 09 0c 75 08 95 06 26 ff 00 b1 02 85 0b 09 0b 95 02 b1 02 85 11 09 11 b1 02 85 15 09 15 95 05 b1 02 85 18 09 18 95 0c b1 02 c0 05 0d 09 04 a1 01 85 03 06 00 ff 09 01 75 10 95 01 15 00 27 ff ff 00 00 81 02 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 7f 0b 26 80 25 81 02 09 31 46 78 06 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 7f 0b 26 80 25 81 02 09 31 46 78 06 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 54 95 01 75 08 81 02 09 56 75 20 95 01 27 ff ff ff 0f 81 02 85 04 09 55 75 08 95 01 25 0b b1 02 85 0a 06 00 ff 09 03 15 00 b1 02 85 1b 06 00 ff 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 05 01 09 02 a1 01 85 02 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 75 01 95 02 81 02 95 06 81 03 05 01 09 30 09 31 15 81 25 7f 75 08 95 02 81 06 c0 c0')


class Testn_trig_1b96_1000(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test n_trig_1b96_1000', rdesc='75 08 15 00 26 ff 00 06 0b ff 09 0b a1 01 95 0f 09 29 85 29 b1 02 95 1f 09 2a 85 2a b1 02 95 3e 09 2b 85 2b b1 02 95 fe 09 2c 85 2c b1 02 96 fe 01 09 2d 85 2d b1 02 95 02 09 48 85 48 b1 02 95 0f 09 2e 85 2e 81 02 95 1f 09 2f 85 2f 81 02 95 3e 09 30 85 30 81 02 95 fe 09 31 85 31 81 02 96 fe 01 09 32 85 32 81 02 75 08 96 fe 0f 09 35 85 35 81 02 c0 05 0d 09 02 a1 01 85 01 09 20 35 00 a1 00 09 32 09 42 09 44 09 3c 09 45 15 00 25 01 75 01 95 05 81 02 95 03 81 03 05 01 09 30 75 10 95 01 a4 55 0e 65 11 46 03 0a 26 80 25 81 02 09 31 46 a1 05 26 20 1c 81 02 b4 05 0d 09 30 26 00 01 81 02 06 00 ff 09 01 81 02 c0 85 0c 06 00 ff 09 0c 75 08 95 06 26 ff 00 b1 02 85 0b 09 0b 95 02 b1 02 85 11 09 11 b1 02 85 15 09 15 95 05 b1 02 85 18 09 18 95 0c b1 02 c0 05 0d 09 04 a1 01 85 03 06 00 ff 09 01 75 10 95 01 15 00 27 ff ff 00 00 81 02 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 03 0a 26 80 25 81 02 09 31 46 a1 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 03 0a 26 80 25 81 02 09 31 46 a1 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 54 95 01 75 08 81 02 09 56 75 20 95 01 27 ff ff ff 0f 81 02 85 04 09 55 75 08 95 01 25 0b b1 02 85 0a 06 00 ff 09 03 15 00 b1 02 85 1b 06 00 ff 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 05 01 09 02 a1 01 85 02 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 75 01 95 02 81 02 95 06 81 03 05 01 09 30 09 31 15 81 25 7f 75 08 95 02 81 06 c0 c0')


class Testsharp_04dd_9681(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test sharp_04dd_9681', rdesc='06 00 ff 09 01 a1 01 75 08 26 ff 00 15 00 85 06 95 3f 09 01 91 02 85 05 95 3f 09 01 81 02 c0 05 0d 09 04 a1 01 85 81 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 07 81 03 75 08 09 51 95 01 81 02 05 01 65 11 55 0f 35 00 46 b0 01 26 80 07 75 10 09 30 81 02 46 f3 00 26 38 04 09 31 81 02 05 0d 09 48 09 49 26 ff 00 95 02 75 08 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 07 81 03 75 08 09 51 95 01 81 02 05 01 65 11 55 0f 35 00 46 b0 01 26 80 07 75 10 09 30 81 02 46 f3 00 26 38 04 09 31 81 02 05 0d 09 48 09 49 26 ff 00 95 02 75 08 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 07 81 03 75 08 09 51 95 01 81 02 05 01 65 11 55 0f 35 00 46 b0 01 26 80 07 75 10 09 30 81 02 46 f3 00 26 38 04 09 31 81 02 05 0d 09 48 09 49 26 ff 00 95 02 75 08 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 07 81 03 75 08 09 51 95 01 81 02 05 01 65 11 55 0f 35 00 46 b0 01 26 80 07 75 10 09 30 81 02 46 f3 00 26 38 04 09 31 81 02 05 0d 09 48 09 49 26 ff 00 95 02 75 08 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 07 81 03 75 08 09 51 95 01 81 02 05 01 65 11 55 0f 35 00 46 b0 01 26 80 07 75 10 09 30 81 02 46 f3 00 26 38 04 09 31 81 02 05 0d 09 48 09 49 26 ff 00 95 02 75 08 81 02 c0 05 0d 09 56 55 0c 66 01 10 47 ff ff 00 00 27 ff ff 00 00 75 10 95 01 81 02 09 54 95 01 75 08 15 00 25 0a 81 02 85 84 09 55 b1 02 85 87 06 00 ff 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 09 0e a1 01 85 83 09 23 a1 02 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0 05 01 09 02 a1 01 09 01 a1 00 85 80 05 09 19 01 29 01 15 00 25 01 95 01 75 01 81 02 95 01 75 07 81 01 05 01 65 11 55 0f 09 30 26 80 07 35 00 46 66 00 75 10 95 01 81 02 09 31 26 38 04 35 00 46 4d 00 81 02 c0 c0')


class Testsipodev_0603_0002(BaseTest.TestPTP):
    def _create_device(self):
        return PTP('uhid test sipodev_0603_0002', type='clickpad', rdesc='05 01 09 02 a1 01 85 03 09 01 a1 00 05 09 19 01 29 02 25 01 75 01 95 02 81 02 95 06 81 03 05 01 09 30 09 31 15 80 25 7f 75 08 95 02 81 06 c0 c0 05 0d 09 05 a1 01 85 04 09 22 a1 02 15 00 25 01 09 47 09 42 95 02 75 01 81 02 75 01 95 02 81 03 95 01 75 04 25 05 09 51 81 02 05 01 15 00 26 44 0a 75 0c 55 0e 65 11 09 30 35 00 46 ac 03 95 01 81 02 46 fe 01 26 34 05 75 0c 09 31 81 02 05 0d c0 55 0c 66 01 10 47 ff ff 00 00 27 ff ff 00 00 75 10 95 01 09 56 81 02 09 54 25 0a 95 01 75 04 81 02 75 01 95 03 81 03 05 09 09 01 25 01 75 01 95 01 81 02 05 0d 85 0a 09 55 09 59 75 04 95 02 25 0f b1 02 85 0b 09 60 75 01 95 01 15 00 25 01 b1 02 95 07 b1 03 85 09 06 00 ff 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 05 0d 09 0e a1 01 85 06 09 22 a1 02 09 52 15 00 25 0a 75 08 95 01 b1 02 c0 09 22 a1 00 85 07 09 57 09 58 75 01 95 02 25 01 b1 02 95 06 b1 03 c0 c0 05 01 09 0c a1 01 85 08 15 00 25 01 09 c6 75 01 95 01 81 06 75 07 81 03 c0 05 01 09 80 a1 01 85 01 15 00 25 01 75 01 0a 81 00 0a 82 00 0a 83 00 95 03 81 06 95 05 81 01 c0 06 0c 00 09 01 a1 01 85 02 25 01 15 00 75 01 0a b5 00 0a b6 00 0a b7 00 0a cd 00 0a e2 00 0a a2 00 0a e9 00 0a ea 00 95 08 81 02 0a 83 01 0a 6f 00 0a 70 00 0a 88 01 0a 8a 01 0a 92 01 0a a8 02 0a 24 02 95 08 81 02 0a 21 02 0a 23 02 0a 96 01 0a 25 02 0a 26 02 0a 27 02 0a 23 02 0a b1 02 95 08 81 02 c0 06 00 ff 09 01 a1 01 85 05 15 00 26 ff 00 19 01 29 02 75 08 95 05 b1 02 c0')


class Testsynaptics_06cb_1d10(BaseTest.TestWin8Multitouch):
    def _create_device(self):
        return Digitizer('uhid test synaptics_06cb_1d10', rdesc='05 01 09 02 a1 01 85 02 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 75 01 95 02 81 02 95 06 81 03 05 01 09 30 09 31 75 08 95 02 15 81 25 7f 35 81 45 7f 55 0e 65 11 81 06 c0 c0 05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 07 81 03 75 08 09 51 15 01 26 ff 00 95 01 81 42 05 01 15 00 26 3c 0c 75 10 55 0e 65 11 09 30 35 12 46 2a 0c 81 02 09 31 15 00 26 f1 06 35 12 46 df 06 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 07 81 03 75 08 09 51 15 01 26 ff 00 95 01 81 42 05 01 15 00 26 3c 0c 75 10 55 0e 65 11 09 30 35 12 46 2a 0c 81 02 09 31 15 00 26 f1 06 35 12 46 df 06 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 07 81 03 75 08 09 51 15 01 26 ff 00 95 01 81 42 05 01 15 00 26 3c 0c 75 10 55 0e 65 11 09 30 35 12 46 2a 0c 81 02 09 31 15 00 26 f1 06 35 12 46 df 06 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 07 81 03 75 08 09 51 15 01 26 ff 00 95 01 81 42 05 01 15 00 26 3c 0c 75 10 55 0e 65 11 09 30 35 12 46 2a 0c 81 02 09 31 15 00 26 f1 06 35 12 46 df 06 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 07 81 03 75 08 09 51 15 01 26 ff 00 95 01 81 42 05 01 15 00 26 3c 0c 75 10 55 0e 65 11 09 30 35 12 46 2a 0c 81 02 09 31 15 00 26 f1 06 35 12 46 df 06 81 02 c0 05 0d 05 0d 55 0c 66 01 10 47 ff ff 00 00 27 ff ff 00 00 75 10 95 01 09 56 81 02 09 54 95 01 75 08 15 00 25 0f 81 02 85 08 09 55 b1 03 85 07 06 00 ff 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 06 00 ff 09 01 a1 01 85 09 09 02 15 00 26 ff 00 75 08 95 3f 91 02 85 0a 09 03 15 00 26 ff 00 75 08 95 05 91 02 85 0b 09 04 15 00 26 ff 00 75 08 95 3d 81 02 85 0c 09 05 15 00 26 ff 00 75 08 95 01 81 02 85 0f 09 06 15 00 26 ff 00 75 08 95 01 b1 02 c0')


if __name__ == '__main__':
    main(sys.argv[1:])
