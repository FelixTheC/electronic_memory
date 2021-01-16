#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@created: 11.01.21
@author: felix
"""
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor as PoolExecutor
from datetime import datetime as dt
from itertools import zip_longest
from pathlib import Path
from queue import Queue
from typing import List
from typing import Tuple
from typing import Union

import RPi.GPIO as GPIO

debug_file = Path('debug.log').absolute().open('a')


LED_OFF = GPIO.HIGH
LED_ON = GPIO.LOW

NULL = object()
NOT_PUSHED = object()


class Config:
    __slots__ = ('leds', 'btns', 'combined')
    config_file = Path('config.json').absolute()

    def __init__(self):
        if not self.config_file.exists():
            raise RuntimeError('For a successful usage create a config.json first.')
        data = json.loads(self.config_file.read_text())
        self.leds = [v['Led'] for v in data.values()]
        self.btns = [v['Btn'] for v in data.values()]

        self.combined = [(led, btn) for led, btn in zip(self.leds, self.btns)]

    def check_unique_gpio_pin(self):
        if len(self.leds) != len(set(self.leds)):
            raise RuntimeWarning('Please check led pin values in config file.')
        if len(self.btns) != len(set(self.btns)):
            raise RuntimeWarning('Please check btn pin values in config file.')


class MemoryGame:

    level: int = 1
    level_complete: Union[bool, object] = NULL

    led_sequence: List[int]
    btn_sequence: List[int]

    pushed_btn: Queue = Queue()
    time_for_move: float = 15.0
    restarting_game: bool = False

    config: Config = Config()

    def __init__(self):
        self.setup()
        self.warm_up()

    def let_all_leds_blink(self) -> None:
        [self.led_blink(led, .5) for led in self.config.leds]

    @staticmethod
    def led_blink(led: int, sleep_time: float) -> None:
        GPIO.output(led, LED_ON)
        time.sleep(sleep_time)
        GPIO.output(led, LED_OFF)

    def generate_sequence(self):
        sequence = random.choices(self.config.combined, k=self.level)
        self.led_sequence = [seq[0] for seq in sequence]
        self.btn_sequence = [seq[1] for seq in sequence]

    def start_round(self):
        self.generate_sequence()
        self.let_all_leds_blink()
        time.sleep(1)
        for led in self.led_sequence:
            self.led_blink(led, 5)
            time.sleep(.5)
        print(f'{dt.now()}: {self.led_sequence = }', file=debug_file, flush=True)

    def check_pushed_btn(self):
        if not self.pushed_btn.empty() and len(self.btn_sequence) > 0:
            check = []
            for btn, required_btn in zip_longest(self.pushed_btn.queue,
                                                 self.btn_sequence,
                                                 fillvalue=NOT_PUSHED):
                if btn is not NOT_PUSHED:
                    if btn != required_btn:
                        self.level_complete = False
                    else:
                        check.append(True)
                else:
                    check.append(False)
                    continue

            if all(check):
                self.level_complete = True

    def _check_btn(self, val: Tuple[int, int]):
        led, btn = val
        time.sleep(.01)
        if not self.restarting_game:
            if GPIO.input(btn) == GPIO.LOW:
                self.pushed_btn.queue.append(btn)
                self.led_blink(led, 1)
                self.check_pushed_btn()

    def check_btn_gpio_input(self):
        combined = self.config.combined
        while True:
            with PoolExecutor() as executor:
                for val in combined:
                    executor.submit(self._check_btn, val)
            if not self.restarting_game:
                self.time_for_move -= .01
            time.sleep(.01)

    def check_level_state(self):
        while True:
            if self.level_complete is NULL:
                time.sleep(.1)
            if self.level_complete is True:
                self.level += 1
                self.start_round()
                self.level_complete = NULL
                self.pushed_btn.queue.clear()
                self.time_for_move = 15.0
            elif self.level > 10:
                self.reset_game()
            elif self.level_complete is False:
                self.reset_game()
            elif self.time_for_move <= 0:
                self.reset_game()
            else:
                time.sleep(.1)

    def reset_game(self):
        self.restarting_game = True
        self.level = 1
        self.time_for_move = 15.0
        self.let_all_leds_blink()
        self.let_all_leds_blink()
        self.start_round()
        self.level_complete = NULL
        self.pushed_btn.queue.clear()
        self.restarting_game = False

    def run(self) -> None:
        threads = []
        with PoolExecutor() as executor:
            threads.append(executor.submit(self.check_btn_gpio_input))
            threads.append(executor.submit(self.check_level_state))
        return

    @staticmethod
    def setup_led(led_pin: int) -> None:
        GPIO.setup(led_pin, GPIO.OUT)
        GPIO.output(led_pin, LED_OFF)
        return

    @staticmethod
    def setup_btn(btn_pin: int) -> None:
        # Set BtnPin's mode is input, and pull up to high level(3.3V)
        GPIO.setup(btn_pin,
                   GPIO.IN,
                   pull_up_down=GPIO.PUD_UP)
        return

    def setup(self) -> None:
        GPIO.setmode(GPIO.BCM)
        # using breakout board pin numbering
        [self.setup_led(led) for led in self.config.leds]
        [self.setup_btn(btn) for btn in self.config.btns]
        return

    def warm_up(self, sleeping_time: float = .5) -> None:
        for led in self.config.leds:
            GPIO.output(led, LED_ON)
            time.sleep(sleeping_time)
            GPIO.output(led, LED_OFF)
        return


def game():
    mem_gme = MemoryGame()
    mem_gme.start_round()
    mem_gme.run()


if __name__ == '__main__':
    try:
        game()
    except KeyboardInterrupt:
        debug_file.close()
    finally:
        GPIO.cleanup()
