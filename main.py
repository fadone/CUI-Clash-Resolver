import PyPDF2
import camelot

import pandas as pd
from tabulate import tabulate

FILE = "timetable.pdf"
# Class | Day | Slot | Room/Lab | Course | Teacher


def process_pdf(file):
    reader = PyPDF2.PdfFileReader(file)
    tables = camelot.read_pdf(file, copy_text=['h'], pages="1-end")
    courses = []

    for idx, table in enumerate(tables):
        class_ = reader.getPage(idx).extractText().split("\n")[-2]
        tab = table.df

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

    courses_df = pd.DataFrame(courses)
    courses_df.columns = ["class", "day", "slot", "room", "course", "teacher"]
    return courses_df


def process_courses_from_timetable(selected_courses, all_courses):
    for idx, course in selected_courses.iterrows():
        class_labs = labs.loc[labs['class'] == course["class"]]
        for idy, lab in class_labs.iterrows():
            # if course["course"] in lab["course"]:
            if match_lab(course["course"], lab["course"]):
                selected_courses = selected_courses.append(lab, ignore_index=True)
    new_ = pd.merge(selected_courses, all_courses, how="inner", left_on=["class", "course", "teacher"],
                    right_on=["class", "course", "teacher"])
    return new_


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
            timetable.at[day, slot] = cell + "\n---CLASH---\n" + "{}\n{}\n{}".format(room, course, teacher)
    return timetable


def course_selection(courses):
    selected = []
    while True:
        num = int(input("Select your courses(-1): "))
        if num == -1:
            break

        try:
            sel = courses.iloc[num]
        except IndexError:
            print("Wrong number! Please try again!")
            continue
        add = True
        for i in selected:
            if i.equals(sel):
                add = False
                break
        if add:
            selected.append(sel)
            print("{} selected!".format(sel.to_string()))
            print()
        else:
            print("Course already added!")
    return selected


def match_lab(course, lab):
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


print("""------------------
CUI CLASH RESOLVER
------------------ """)
print("Processing timetable.pdf! Please wait...")

df = process_pdf(FILE)

while True:
    option = input("""
    1. Check clashes
    0. Exit
    
    Enter:""")
    if option == "1":
        pass
    elif option == "0":
        break
    else:
        print("Wrong option!")
        continue

    labs = df[df['course'].str.contains('Lab')]
    labs = labs.drop_duplicates(["class", "course", "teacher"]).reset_index()[["class", "course", "teacher"]]
    print(tabulate(labs, headers='keys', tablefmt='psql'))

    unique = df[df['course'].str.contains("Lab") == False]
    unique = unique.drop_duplicates(["class", "course", "teacher"]).reset_index()[["class", "course", "teacher"]]

    print("All Courses:")
    print(tabulate(unique, headers='keys', tablefmt='psql'))

    while True:
        selected = course_selection(unique)
        print("Your courses:")
        selected = pd.DataFrame(selected, columns=["class", "course", "teacher"])
        print(tabulate(selected, headers='keys', tablefmt='psql'))
        ans = input("Are your courses okay?(y/n): ")
        if ans == "y":
            break

    print()
    print("Your TimeTable:")
    selected_course = process_courses_from_timetable(selected, df)
    new_timetable = create_timetable(selected_course)
    print(tabulate(new_timetable, headers='keys', tablefmt='psql'))

    export = input("Export timetable to excel(y/n):")
    if export == "y":
        new_timetable.to_csv("timetable.csv")
        # writer = pd.ExcelWriter('timetable.xlsx')
        # new_timetable.to_excel(writer, sheet_name='time_table')

        # writer.sheets['time_table'].set_column(1, 5, 20)

        # writer.save()
        print("timetable.xlsx saved!")
