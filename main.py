import sys
from PySide6.QtWidgets import QApplication, QWidget

app = QApplication(sys.argv)
w = QWidget()
w.resize(300, 120)
w.show()
sys.exit(app.exec())