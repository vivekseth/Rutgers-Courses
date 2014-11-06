import json
import requests
from joblib import Parallel, delayed  
import multiprocessing

# -- Globals --

SUBJECT_URL = "https://sis.rutgers.edu/soc/subjects.json?semester=92014&campus=NB&level=U"
COURSES_URL_TEMPLATE = "https://sis.rutgers.edu/soc/courses.json?subject=%(subject_code)s&semester=92014&campus=NB&level=U"
OUTPUT_TEMPLATE = "\"%(subject_name)s\", \"%(course_name)s\", %(course_number)s, \"%(instructor_name)s\", \"%(meeting_day)s\", %(meeting_time)s, %(meeting_location)s"

# -- Classes --

class Subject(object):
	def __init__(self, code, name):
		super(Subject, self).__init__()
		self.code = code
		self.name = name
		self.courses = []
	def setCourses(self, courses):
		self.courses = courses
	def csv(self):
		for c in self.courses:
			for s in c.sections:
				for m in s.meetings:
					format_dict = {}
					format_dict['subject_name'] = self.name
					format_dict['course_name'] = c.name
					format_dict['course_number'] = c.code
					format_dict['instructor_name'] = s.instructors[0] if len(s.instructors) > 0 else 'N/A'
					format_dict['meeting_day'] = m.days
					format_dict['meeting_time'] = m.time
					format_dict['meeting_location'] = m.location
					print OUTPUT_TEMPLATE % format_dict

class Course(object):
	def __init__(self, name, code, sections):
		super(Course, self).__init__()
		self.name = name
		self.code = code
		self.sections = sections

class Section(object):
	def __init__(self, code, instructors, meetings):
		super(Section, self).__init__()
		self.code = code
		self.instructors = instructors
		self.meetings = meetings
	
class Meeting(object):
	def __init__(self, days, time, location):
		super(Meeting, self).__init__()
		self.days = days
		self.time = time
		self.location = location

# -- API Requests --

def getSubjectData():
	r = requests.get(SUBJECT_URL)
	if r.status_code == 200:
		try:
			return json.loads(r.text)
		except Exception, e:
			print e
	return None

def getCourseData(subject):
	r = requests.get(COURSES_URL_TEMPLATE % {'subject_code': subject})
	if r.status_code == 200:
		try:
			return json.loads(r.text)
		except Exception, e:
			print e
	return None

# -- Parsing JSON --

def parseSubjects(subjectData):
	subject_list = []
	for entry in subjectData:
		s = Subject(entry['code'], entry['description'])
		subject_list.append(s)
	return subject_list

def parseCourses(courseData):
	course_list = []
	for entry in courseData:
		sections = parseSections(entry['sections'])
		c = Course(entry['title'], entry['courseNumber'], sections)
		course_list.append(c)
	return course_list

def parseSections(sectionData):
	section_list = []
	for entry in sectionData:
		instructors = []
		instructor_data = entry['instructors']
		for i in instructor_data:
			instructors.append(i['name'])
		meeting_list = parseMeetings(entry['meetingTimes'])
		s = Section(entry['number'], instructors, meeting_list)
		section_list.append(s)
	return section_list

def parseMeetings(meetingData):
	meeting_list = []
	for entry in meetingData:
		if not entry['startTime'] or not entry['endTime']:
			continue
		if not entry['campusName'] or not entry['buildingCode'] or not entry['roomNumber']:
			continue
		days = entry['meetingDay']
		time = entry['startTime'] + " - " + entry['endTime']
		location = entry['campusName']+':'+entry['buildingCode']+':'+entry['roomNumber'];
		m = Meeting(days, time, location)
		meeting_list.append(m)
	return meeting_list
 
# -- Parallelization -- 

def setCoursesForSubject(s):
	s.setCourses(parseCourses(getCourseData(s.code)))
	return s

# -- Main -- 

def downloadSubjectsAndParse():
	subjectData = getSubjectData()
	subject_list = parseSubjects(subjectData)
	# setCoursesForSubject(subject_list[0])
	# return [subject_list[0]]
	num_cores = multiprocessing.cpu_count()
	out = Parallel(n_jobs=num_cores)(delayed(setCoursesForSubject)(subject_list[i]) for i in range(len(subject_list))) 
	return out

if __name__ == '__main__':
	subjects = downloadSubjectsAndParse()
	for s in subjects:
		s.csv()