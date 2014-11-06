import json
import requests
from joblib import Parallel, delayed  
import multiprocessing
import re

# -- Globals --

SUBJECT_URL = "https://sis.rutgers.edu/soc/subjects.json?semester=92014&campus=NB&level=U"
COURSES_URL_TEMPLATE = "https://sis.rutgers.edu/soc/courses.json?subject=%(subject_code)s&semester=92014&campus=NB&level=U"
OUTPUT_TEMPLATE = "\"%(subject_name)s\", \"%(course_name)s\", %(course_number)s, \"%(instructor_name)s\", \"%(meeting_day)s\", %(meeting_time)s, %(meeting_location)s"

PREREQ_TEST_1 = "Any Course EQUAL or GREATER Than: (01:640:026 )"
PREREQ_TEST_2 = "(01:640:135 )<em> OR </em>(01:640:151 )<em> OR </em>(01:640:153 INTENSIVE CALC I)<em> OR </em>(01:640:191 HONORS CALCULUS I) "
PREREQ_TEST_3 = "((01:198:112  or 14:332:351 ) and (01:198:211 ))<em> OR </em> ((01:198:112  or 14:332:351 ) and (14:332:331 ))"


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
	def __init__(self, name, code, sections, prereqs):
		super(Course, self).__init__()
		self.name = name
		self.code = code
		self.sections = sections
		self.prereqs = prereqs

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

# -- Prequisite Evaluator --

"""
Any Course EQUAL or GREATER Than: (01:640:026 )
(01:640:135 )<em> OR </em>(01:640:151 )<em> OR </em>(01:640:153 INTENSIVE CALC I)<em> OR </em>(01:640:191 HONORS CALCULUS I) 
((01:198:112  or 14:332:351 ) and (01:198:211 ))<em> OR </em> ((01:198:112  or 14:332:351 ) and (14:332:331 ))

'((01:198:112  or 14:332:351 ) and (01:198:211 ))'
EXP
TERM
FACTOR
(EXP)
(TERM)
(FACTOR and FACTOR)
((EXP) and (EXP))
((TERM or TERM) and (TERM))
((FACTOR or FACTOR) and (FACTOR))
((COURSE_ID  or COURSE_ID ) and (COURSE_ID ))
((01:198:112  or 14:332:351 ) and (01:198:211 ))


EXP => TERM | TERM or TERM
TERM => FACTOR | FACTOR and FACTOR
FACTOR => `COURSE_ID ` | (EXP)
COURSE_ID => `SCHOOL:SUBJECT:COURSE`
SCHOOL => `\d+`
SUBJECT => `\d+`
COURSE => `\d+`

"""

def stringsOnSameParenLevel(e):
	level = 0
	sameLevelList = []
	currString = ""
	for i in range(len(e)):
		if e[i] == '(':
			if len(currString) > 0 and level == 0:
				sameLevelList.append(currString)
				currString = ""
			level = level + 1
		currString+=e[i]
		if e[i] == ')':
			if len(currString) > 0 and level == 1:
				sameLevelList.append(currString)
				currString = ""
			level = level - 1
	if len(currString) > 0:
		sameLevelList.append(currString)
	return sameLevelList

def parsePrereqString(inputString):
	e = inputString.strip()
	if (e.find('Any Course EQUAL or GREATER Than: ') >= 0):
		return parsePrereqString(e.split('Any Course EQUAL or GREATER Than: ')[1])
	if (re.search('<em> AND </em>.*<em> AND </em>.*<em> AND </em>', e)):
		e = re.sub(r'(^.*?)<em> AND </em>(.*?)<em> AND </em>(.*?)<em> AND </em>(.*?$)', r'(\1 and (\2 and (\3 and \4)))', e)
	if (re.search('<em> AND </em>.*<em> AND </em>', e)):
		e = re.sub(r'(^.*?)<em> AND </em>(.*?)<em> AND </em>(.*?$)', r'(\1 and (\2 and \3))', e)
	if (re.search('<em> AND </em>', e)):
		e = re.sub(r'(^.*?)<em> AND </em>(.*?$)', r'(\1 and \2)', e)

	sameLevelStrings = stringsOnSameParenLevel(e)
	if len(sameLevelStrings) == 1:
		if (sameLevelStrings[0][0] == '('):
			return parsePrereqString(e[1:-1]) #remove outer parens
		else:
			#branch 1
			andSplitString = e.split('and')
			if len(andSplitString) == 2:
				courseString1 = re.search('\d+:\d+:\d+', andSplitString[0]).group(0)
				courseString2 = re.search('\d+:\d+:\d+', andSplitString[1]).group(0)
				return AndPrerequisite(CoursePrerequisite(courseString1), CoursePrerequisite(courseString2))
			#branch 2
			orSplitString = e.split('or')
			if len(orSplitString) == 2:
				courseString1 = re.search('\d+:\d+:\d+', orSplitString[0]).group(0)
				courseString2 = re.search('\d+:\d+:\d+', orSplitString[1]).group(0)
				return OrPrerequisite(CoursePrerequisite(courseString1), CoursePrerequisite(courseString2))
			#branch 3
			return CoursePrerequisite(andSplitString[0])
	elif len(sameLevelStrings) == 3:
		operator = sameLevelStrings[1] # middle element
		if (operator.find('and') >= 0):
			return AndPrerequisite(parsePrereqString(sameLevelStrings[0]), parsePrereqString(sameLevelStrings[2]))
		elif (operator.find('or') >= 0):
			return OrPrerequisite(parsePrereqString(sameLevelStrings[0]), parsePrereqString(sameLevelStrings[2]))
		else:
			print 'ERROR: '+e
	else:
		print 'ERROR: '+e

def parsePrereqOptions(e):
	optionStrings = e.split('<em> OR </em>')
	prereqOptions = []
	for o in optionStrings:
		p = parsePrereqString(o)
		if p:
			prereqOptions.append(p)
	for p in prereqOptions:
		p.evaluate(3)

class Prerequisite(object):
	def __init__(self):
		super(Prerequisite, self).__init__()
	def evaluate(self, course_set):
		return False;

class AndPrerequisite(Prerequisite):
	def __init__(self, p1, p2):
		super(AndPrerequisite, self).__init__()
		self.p1 = p1
		self.p2 = p2
	def evaluate(self, course_set):
		self.p1.evaluate(course_set)
		self.p2.evaluate(course_set)

class OrPrerequisite(Prerequisite):
	def __init__(self, p1, p2):
		super(OrPrerequisite, self).__init__()
		self.p1 = p1
		self.p2 = p2
	def evaluate(self, course_set):
		self.p1.evaluate(course_set)
		self.p2.evaluate(course_set)

class CoursePrerequisite(Prerequisite):
	def __init__(self, course):
		super(CoursePrerequisite, self).__init__()
		self.course = course
	def evaluate(self, course_set):
		return 
		# print self.course

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
		prereqs = parsePrereqOptions(entry['preReqNotes']) if entry['preReqNotes'] != None else []
		c = Course(entry['title'], entry['courseNumber'], sections, prereqs)
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
	print subjects