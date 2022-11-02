import os
import time

import PyPDF2
import bs4
import camelot
import pandas as pd
from PyQt5.QtCore import QObject, pyqtSignal, QThread, QAbstractTableModel, Qt
from PyQt5.QtWidgets import QMainWindow, QApplication, QFileDialog, QMessageBox, \
    QTableWidgetItem, QHeaderView
from PyQt5 import QtGui
import sys
import cgitb
import requests

import main_window
import timetable_window

cgitb.enable(format='text')
departments = ["CS", "EE", "CE", "ME", "MS"]

DAYS = {
    "Monday": "Mon",
    "Tuesday": "Tue",
    "Wednesday": "Wed",
    "Thursday": "Thu",
    "Friday": "Fri",
    "Saturday": "Sat",
    "Sunday": "Sun",
}

SLOTS = ["1st Slot", "2nd Slot", "3rd Slot", "4th Slot", "5th Slot"]


class UI(QMainWindow, main_window.Ui_MainWindow):
    def __init__(self):
        super(UI, self).__init__()
        self.dialog = None
        # uic.loadUi(resource_path("main.ui"), self)
        self.setupUi(self)

        self.filename = ""
        self.thread = None
        self.worker = None
        self.courses = None
        self.statusBar = self.statusBar()
        self.setStatusBar(self.statusBar)

        self.reg_courses = None
        self.labs = None
        self.selected_df = pd.DataFrame(columns=["class", "course", "teacher"])
        self.selected_list = []
        self.deptCB.addItems(departments)
        self.browseBtn.clicked.connect(self.browse_pdf)
        self.getBtn.clicked.connect(self.get_data)
        self.addBtn.clicked.connect(self.add_course)
        self.removeBtn.clicked.connect(self.remove_course)
        self.showBtn.clicked.connect(self.show_timetable)
        self.showBtn.setEnabled(False)
        self.searchLE.returnPressed.connect(self.search)
        self.show()

    def search(self):
        search_txt = self.searchLE.text().lower()
        for row in range(self.coursesTable.rowCount()):
            item = self.coursesTable.item(row, 1)
            self.coursesTable.setRowHidden(row, search_txt not in item.text().lower())

    def browse_pdf(self):
        self.filename = QFileDialog.getOpenFileName(self, "Open file", "", "PDF files (*.pdf)")
        self.pathLE.setText(self.filename[0])
        self.upload_pdf()

    def get_data(self):
        data = process_timetable_from_datafurnish()
        self.pdf_process_finished(data)
        self.reset_gui()

    def upload_pdf(self):
        self.thread = QThread()
        self.worker = Worker(self.filename[0])
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.finished.connect(self.pdf_process_finished)
        self.worker.progress.connect(self.update_progress)
        self.thread.start()
        self.disable_gui()
        self.thread.finished.connect(self.reset_gui)

    def show_error(self, message):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setText("Error")
        msg.setInformativeText(message)
        msg.setWindowTitle("Error")
        msg.exec_()

    def disable_gui(self):
        self.browseBtn.setText("Please wait")
        self.browseBtn.setEnabled(False)
        self.showBtn.setEnabled(False)
        self.deptCB.setEnabled(False)
        self.pathLE.setEnabled(False)
        self.statusBar.showMessage("Processing: {}%".format(0))

    def reset_gui(self):
        self.browseBtn.setText("Browse")
        self.browseBtn.setEnabled(True)
        self.showBtn.setEnabled(True)
        self.deptCB.setEnabled(True)
        self.pathLE.setEnabled(True)
        self.statusBar.clearMessage()

    def update_table(self, table, data):
        rows = data.shape[0]
        columns = data.shape[1]
        table.setRowCount(rows)
        table.setColumnCount(columns)
        table.setHorizontalHeaderLabels(data.columns)
        table.setColumnWidth(0, 90)
        table.setColumnWidth(1, 240)
        table.setColumnWidth(2, 160)

        for i in range(rows):
            for j in range(columns):
                table.setItem(i, j, QTableWidgetItem(data.iloc[i, j]))

    def pdf_process_finished(self, data):
        self.courses = data
        self.clean_data()
        self.update_table(self.coursesTable, self.reg_courses)

    def clean_data(self):
        self.labs = self.courses[self.courses['course'].str.contains('Lab')]
        self.labs = self.labs.drop_duplicates(["class", "course", "teacher"]).reset_index()[
            ["class", "course", "teacher"]]

        self.reg_courses = self.courses[self.courses['course'].str.contains("Lab") == False]
        self.reg_courses = self.reg_courses.drop_duplicates(["class", "course", "teacher"]).reset_index()[
            ["class", "course", "teacher"]]

    def add_course(self):
        selected_row = self.coursesTable.currentRow()
        if selected_row == -1:
            return
        course = self.reg_courses.iloc[selected_row]
        self.selected_df = self.selected_df.append(course)
        self.reg_courses = self.reg_courses.drop(course.name)
        self.update_table(self.selectedTable, self.selected_df)
        self.update_table(self.coursesTable, self.reg_courses)
        self.searchLE.clear()
        for row in range(self.coursesTable.rowCount()):
            self.coursesTable.setRowHidden(row, False)

    def remove_course(self):
        selected_row = self.selectedTable.currentRow()
        if selected_row == -1:
            return
        course = self.selected_df.iloc[selected_row]
        self.reg_courses = self.reg_courses.append(course).sort_index()
        self.selected_df = self.selected_df.drop(course.name)

        self.update_table(self.selectedTable, self.selected_df)
        self.update_table(self.coursesTable, self.reg_courses)
        for row in range(self.coursesTable.rowCount()):
            self.coursesTable.setRowHidden(row, False)

    def show_timetable(self):
        selected = self.process_courses_from_timetable(self.selected_df, self.courses)
        timetable = create_timetable(selected)
        self.dialog = TimeTableWindow(timetable)
        self.dialog.show()

    def process_courses_from_timetable(self, selected_courses, all_courses):
        for idx, course in selected_courses.iterrows():
            class_labs = self.labs.loc[self.labs['class'] == course["class"]]
            for idy, lab in class_labs.iterrows():
                # if course["course"] in lab["course"]:
                if self.match_lab(course["course"], lab["course"]):
                    selected_courses = selected_courses.append(lab, ignore_index=True)
        new_ = pd.merge(selected_courses, all_courses, how="inner", left_on=["class", "course", "teacher"],
                        right_on=["class", "course", "teacher"])
        return new_

    def match_lab(self, course, lab):
        course = course.split(" ")
        lab = lab.replace(".", "").replace(" (Lab)", "").split(" ")
        lab = [l for l in lab if l != " "]
        course = [c for c in course if c != " "]

        lab_len = len(lab)
        r = 0
        for l in lab:
            for c in course:
                if l in c:
                    r += 1
                    break
        if lab_len == r:
            return True
        else:
            return False

    def update_progress(self, n):
        self.statusBar.showMessage("Processing: {}%".format(n))


class TimeTableModel(QAbstractTableModel):

    def __init__(self, data):
        super(TimeTableModel, self).__init__()
        self._data = data

    def data(self, index, role):
        if role == Qt.DisplayRole:
            value = self._data.iloc[index.row(), index.column()]
            return str(value)
        if role == Qt.BackgroundRole:
            value = str(self._data.iloc[index.row(), index.column()])
            if value is None:
                return
            if "CLASH" in value:
                return QtGui.QColor('yellow')
        if role == Qt.TextAlignmentRole:
            return Qt.AlignCenter

    def rowCount(self, index):
        return self._data.shape[0]

    def columnCount(self, index):
        return self._data.shape[1]

    def headerData(self, section, orientation, role):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return str(self._data.columns[section])
            if orientation == Qt.Vertical:
                return str(self._data.index[section])


class TimeTableWindow(QMainWindow, timetable_window.Ui_MainWindow):

    def __init__(self, data, parent=None):
        super(TimeTableWindow, self).__init__(parent)
        self.setupUi(self)
        # uic.loadUi(resource_path("timetable.ui"), self)

        self.model = TimeTableModel(data)
        self.timeTableView.setModel(self.model)
        self.timeTableView.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.timeTableView.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)


class PandasModel(QAbstractTableModel):

    def __init__(self, data):
        QAbstractTableModel.__init__(self)
        self._data = data

    def rowCount(self, parent=None):
        return self._data.shape[0]

    def columnCount(self, parnet=None):
        return self._data.shape[1]

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid():
            if role == Qt.DisplayRole:
                return str(self._data.iloc[index.row(), index.column()])
        return None

    def headerData(self, col, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self._data.columns[col]
        return None


class Worker(QObject):
    finished = pyqtSignal(pd.DataFrame)
    progress = pyqtSignal(int)

    def __init__(self, filename, parent=None):
        QThread.__init__(self, parent)
        self.filename = filename

    def run(self):
        """Long-running task."""
        courses = process_pdf(self.filename, self.progress)
        self.finished.emit(courses)


def process_timetable_from_datafurnish():
    url = "https://portal.cuiwah.edu.pk/"
    url2 = "https://portal.cuiwah.edu.pk/DataFurnish3.php?page=1000"
    session = requests.Session()
    response = session.get(url, verify=False)
    time.sleep(1)
    response = session.get("https://portal.cuiwah.edu.pk/dfGeneral.php?rid=560127792&view=TableSimple&page=1000", verify=False)
    time.sleep(1)
    response = session.get(url2, verify=False)
    soup = bs4.BeautifulSoup(response.content, 'html.parser')
    print(soup.prettify())
    trs = soup.find_all('tr')
    data = []
    for tr in trs[6:-1]:
        tds = tr.find_all('td')
        row = []
        for td in tds:
            row.append(td.text.strip())

        if row[0] != "BSE" and row[0] != "BCS" and row[0] != "BEE":
            continue
        class_ = f"{row[0]}-{row[1]}{row[2]}"
        day = DAYS[row[4]]
        slot = SLOTS[int(row[9]) - 1]
        room = row[6]
        course = row[3]
        teacher = row[7]
        class_type = row[10]
        if class_type == "Lab":
            course += " (Lab)"
        data.append((class_, day, slot, room, course, teacher))

    df = pd.DataFrame(data, columns=["class", "day", "slot", "room", "course", "teacher"])
    df.sort_values(['class', 'course'], inplace=True)
    return df


def process_pdf(file, progress):
    reader = PyPDF2.PdfFileReader(file)
    courses = []
    total_pages = reader.numPages
    for page in range(total_pages):
        print(f"Page: {page}")
        table = camelot.read_pdf(file, copy_text=['h'], pages="{}".format(page+1))
        class_ = reader.getPage(page).extractText().split("\n")[-1]
        print(table)
        tab = table[0].df
        slots = tab.iloc[0]

        for index, row in tab.iloc[1:].iterrows():
            day = row[0]
            slotno = 0
            for course in row[1:]:
                slotno += 1
                if course != "":
                    slot = slots[slotno].split("\n")[0]
                    attr = course.split("\n")
                    room = attr[0]
                    subject = " ".join(attr[1:len(attr) - 1])
                    teacher = attr[-1]
                    courses.append((class_, day, slot, room, subject, teacher))
        quo = (page+1)/total_pages
        progress.emit(quo*100)

    courses_df = pd.DataFrame(courses)
    courses_df.columns = ["class", "day", "slot", "room", "course", "teacher"]
    return courses_df


def create_timetable(courses):
    timetable = pd.DataFrame(columns=["1st Slot", "2nd Slot", "3rd Slot", "4th Slot", "5th Slot"],
                             index=["Mon", "Tue", "Wed", "Thu", "Fri"]).fillna("")
    for index, row in courses.iterrows():
        class_, day, slot, room, course, teacher = row["class"], row["day"], row["slot"], row["room"], row["course"], \
                                                   row["teacher"]
        cell = timetable[slot].loc[day]
        if cell == "":
            timetable.at[day, slot] = "{} \n {} \n {}".format(room, course, teacher)
        else:
            timetable.at[day, slot] = cell + "\n------CLASH------\n" + "{}\n{}\n{}".format(room, course, teacher)
    return timetable


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


app = QApplication(sys.argv)
window = UI()
app.exec_()
