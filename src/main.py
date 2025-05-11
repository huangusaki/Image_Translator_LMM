import sys 
import os 
from ui .main_window import MainWindow 
from PyQt6 .QtWidgets import QApplication 
def main ():
    app =QApplication (sys .argv )
    window =MainWindow ()
    window .show ()
    sys .exit (app .exec ())
if __name__ =='__main__':
    main ()