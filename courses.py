import json
import requests
from joblib import Parallel, delayed  
import multiprocessing
import re
import pickle
import pygraphviz as pgv

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
	def __repr__(self):
		return self.__str__()
	def __str__(self):
		coursesStrings = ""
		for c in self.courses:
			coursesStrings += str(c) + '\n'
		return "SUBJECT: %s | %s" %(self.name, self.code) + "\n" + coursesStrings + "\n----\n"
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
	def __init__(self, name, code, sections, prereqs, coreCodes):
		super(Course, self).__init__()
		self.name = name
		self.code = code
		self.sections = sections
		self.prereqs = prereqs
		self.coreCodes = coreCodes
	def doesFulfillPrereqs(self, courseCodeSet):
		for p in self.prereqs:
			if p.evaluate(courseCodeSet):
				return True
	def __repr__(self):
		return self.__str__()
	def __str__(self):
		return "%s [%s] (%d) -- %s" %(self.name, self.code, len(self.sections), str(self.coreCodes))

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

class Prerequisite(object):
	def __init__(self):
		super(Prerequisite, self).__init__()
	def evaluate(self, course_set):
		return False;
	def str_exp(self):
		return ""
	def related_courses(self):
		return []

class AndPrerequisite(Prerequisite):
	def __init__(self, p1, p2):
		super(AndPrerequisite, self).__init__()
		self.p1 = p1
		self.p2 = p2
	def evaluate(self, course_set):
		return self.p1.evaluate(course_set) and self.p2.evaluate(course_set)
	def str_exp(self):
		return "(" + self.p1.str_exp() + " and " + self.p2.str_exp() + ")"
	def related_courses(self):
		return self.p1.related_courses() + self.p2.related_courses()

class OrPrerequisite(Prerequisite):
	def __init__(self, p1, p2):
		super(OrPrerequisite, self).__init__()
		self.p1 = p1
		self.p2 = p2
	def evaluate(self, course_set):
		return self.p1.evaluate(course_set) or self.p2.evaluate(course_set)
	def str_exp(self):
		return "(" + self.p1.str_exp() + " or " + self.p2.str_exp() + ")"
	def related_courses(self):
		return self.p1.related_courses() + self.p2.related_courses()

class CoursePrerequisite(Prerequisite):
	def __init__(self, courseCode):
		super(CoursePrerequisite, self).__init__()
		numbers = courseCode.split(':')
		if len(numbers) == 3:
			strippedCourseCode = numbers[1]+':'+numbers[2].split(' ')[0] # to account for possible class descriptor
			self.courseCode = strippedCourseCode.strip()
		else:
			self.courseCode = courseCode.strip()
	def evaluate(self, course_set):
		return self.courseCode in course_set
	def str_exp(self):
		return self.courseCode
	def related_courses(self):
		return [self.courseCode]

class NonePrerequisite(Prerequisite):
	def __init__(self):
		super(NonePrerequisite, self).__init__()
	def evaluate(self, course_set):
		return True;
	def str_exp(self):
		return "<none>"
	def related_courses(self):
		return []

class GreaterThanPrerequisite(CoursePrerequisite):
	def __init__(self, courseCode):
		super(GreaterThanPrerequisite, self).__init__(courseCode)
	def evaluate(self, course_set):
		for c in course_set:
			if c.split(':')[0] == self.courseCode.split(':')[0]:
				if int(c.split(':')[1]) <= int(self.courseCode.split(':')[1]):
					return True
		return False
	def str_exp(self):
		return "<none>"
	def related_courses(self):
		return [self.courseCode]

""" TODO: parse TwoCoursesInSubjectPrerequisite"""
class TwoCoursesInSubjectPrerequisite(object):
	def __init__(self, subjectCode):
		super(TwoCoursesInSubjectPrerequisite, self).__init__()
		self.subjectCode = subjectCode
	def evaluate(self, course_set):
		counter = 0
		for c in course_set:
			s = c.split(':')[0]
			if s == self.subjectCode:
				counter = counter + 1
		if counter >= 2:
			return True
		else:
			return False
	def str_exp(self):
		return "(" + self.subjectCode + ".xxx and "+self.subjectCode + ".xxx)"
	def related_courses(self):
		return []
		
# -- Prequisite Parsing --

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

def parsePrereqString(subject, inputString):
	# TWO Course Within the Subject Area:

	e = inputString.strip()

	if (e.find('TWO Course Within the Subject Area:') >= 0):
		return TwoCoursesInSubjectPrerequisite(subject)
	if (e.find('Any Course EQUAL or GREATER Than: ') >= 0):
		return GreaterThanPrerequisite(e.split('Any Course EQUAL or GREATER Than: ')[1][1:-1])
	
	if (re.search('<em> AND </em>.*<em> AND </em>.*<em> AND </em>', e)):
		e = re.sub(r'(^.*?)<em> AND </em>(.*?)<em> AND </em>(.*?)<em> AND </em>(.*?$)', r'(\1 and (\2 and (\3 and \4)))', e)
	if (re.search('<em> AND </em>.*<em> AND </em>', e)):
		e = re.sub(r'(^.*?)<em> AND </em>(.*?)<em> AND </em>(.*?$)', r'(\1 and (\2 and \3))', e)
	if (re.search('<em> AND </em>', e)):
		e = re.sub(r'(^.*?)<em> AND </em>(.*?$)', r'(\1 and \2)', e)

	sameLevelStrings = stringsOnSameParenLevel(e)
	if len(sameLevelStrings) == 1:
		if (sameLevelStrings[0][0] == '('):
			return parsePrereqString(subject, e[1:-1]) #remove outer parens
		else:
			#branch 1
			andSplitString = e.split('and')
			if len(andSplitString) == 2:
				courseString1 = re.search('\d+:\d+:\d+', andSplitString[0]).group(0)
				courseString2 = re.search('\d+:\d+:\d+', andSplitString[1]).group(0)
				return AndPrerequisite(CoursePrerequisite(courseString1), CoursePrerequisite(courseString2))
			elif len(andSplitString) == 3:
				courseString1 = re.search('\d+:\d+:\d+', andSplitString[0]).group(0)
				courseString2 = re.search('\d+:\d+:\d+', andSplitString[1]).group(0)
				courseString3 = re.search('\d+:\d+:\d+', andSplitString[2]).group(0)
				return AndPrerequisite(CoursePrerequisite(courseString1), AndPrerequisite(CoursePrerequisite(courseString2), CoursePrerequisite(courseString3)))
			#branch 2
			orSplitString = e.split('or')
			if len(orSplitString) == 2:
				courseString1 = re.search('\d+:\d+:\d+', orSplitString[0]).group(0)
				courseString2 = re.search('\d+:\d+:\d+', orSplitString[1]).group(0)
				return OrPrerequisite(CoursePrerequisite(courseString1), CoursePrerequisite(courseString2))
			elif len(orSplitString) == 3:
				courseString1 = re.search('\d+:\d+:\d+', orSplitString[0]).group(0)
				courseString2 = re.search('\d+:\d+:\d+', orSplitString[1]).group(0)
				courseString3 = re.search('\d+:\d+:\d+', orSplitString[2]).group(0)
				return OrPrerequisite(CoursePrerequisite(courseString1), OrPrerequisite(CoursePrerequisite(courseString2), CoursePrerequisite(courseString3)))
			#branch 3
			return CoursePrerequisite(andSplitString[0])
	elif len(sameLevelStrings) == 3:
		operator = sameLevelStrings[1] # middle element
		if (operator.find('and') >= 0):
			return AndPrerequisite(parsePrereqString(subject, sameLevelStrings[0]), parsePrereqString(subject, sameLevelStrings[2]))
		elif (operator.find('or') >= 0):
			return OrPrerequisite(parsePrereqString(subject, sameLevelStrings[0]), parsePrereqString(subject, sameLevelStrings[2]))
		else:
			print 'ERROR: '+e
	else:
		print 'ERROR: '+e

def parsePrereqOptions(subject, e):
	if e == None:
		return [NonePrerequisite()]
	optionStrings = e.split('<em> OR </em>')
	prereqOptions = []
	for o in optionStrings:
		p = parsePrereqString(subject, o)
		if p:
			prereqOptions.append(p)
	return prereqOptions

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
		subject_code = entry['subject']
		sections = parseSections(entry['sections'])
		prereqs = parsePrereqOptions(subject_code, entry['preReqNotes'])
		coreCodes = parseCoreCodes(entry['coreCodes'])
		c = Course(entry['title'], subject_code + ':' + entry['courseNumber'], sections, prereqs, coreCodes)
		course_list.append(c)
	return course_list

def parseCoreCodes(coreCodesData):
	if coreCodesData == None:
		return []
	code_list = []
	for entry in coreCodesData:
		code_list.append(str(entry['code']))
	return code_list

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
 
# -- Main -- 

def setCoursesForSubject(s):
	s.setCourses(parseCourses(getCourseData(s.code)))
	return s

def downloadSubjectsAndParse():
	subjectData = getSubjectData()
	subject_list = parseSubjects(subjectData)
	num_cores = multiprocessing.cpu_count()
	out = Parallel(n_jobs=num_cores)(delayed(setCoursesForSubject)(subject_list[i]) for i in range(len(subject_list))) 
	return out

def fulfillTest(index, courseCode):
	if courseCode not in index:
		print "no matching course found"
		return
	course = index[courseCode]
	for p in course.prereqs:
		print p.str_exp()

	while True:
		temp = raw_input('enter courses: ')
		if temp == 'q':
			return
		courseCodeList = temp.split(',')
		courseSet = set()
		for code in courseCodeList:
			courseSet.add(code.strip())
		if course.doesFulfillPrereqs(courseSet):
			print "YES"
		else:
			print "no :("

def findAllMatchingClasses(subjects, courseSet):
	for s in subjects:
		for c in s.courses:
			if c.doesFulfillPrereqs(courseSet):
				print c

def repl():
	input_list = []
	while True:
		begin_prefix = '--> '
		continue_prefix = '... '
		input_str = raw_input(begin_prefix if len(input_list) == 0 else continue_prefix)
		if input_str == 'QUIT':
			print 'ending REPL'
			break
		elif input_str == '':
			try:
				exec '\n'.join(input_list)
			except Exception, e:
				print 'error'
			input_list = []
		else:
			input_list.append(input_str)

def graph_json(subjects):
	nodes = []
	for s in subjects:
		subject_code = s.code
		for c in s.courses:
			course_code = c.code
			nodes.append({'name':course_code,'group':2})
	# print nodes
	links = []
	for s in subjects:
		subject_code = s.code
		for c in s.courses:
			course_code = c.code
			for p in c.prereqs:
				related_courses = p.related_courses()
				for rc in related_courses:
					
					source_index = -1
					for i, j in enumerate(nodes):
						if j['name'] == course_code:
							source_index = i

					target_index = -1
					for i, j in enumerate(nodes):
						if j['name'] == rc:
							target_index = i

					if source_index > 0 and target_index > 0:
						links.append({"source":source_index,"target":target_index,"value":3},)

	return json.dumps({'nodes': nodes, 'links': links})

def prereq_graph(subjects):
	g = pgv.AGraph(strict=False,directed=False)
	g.graph_attr['overlap'] = False
	g.graph_attr['fontname'] = 'Helvetica'
	g.node_attr['fontname'] = 'Helvetica'
	g.node_attr['shape']='point'
	g.node_attr['color']='white'
	g.graph_attr['repulsiveforce'] = 5.0
	g.graph_attr['K'] = 1.0
	g.graph_attr['bgcolor'] = '0.0 0.0 0.0'

	edges = {}

	for s in subjects:
		subject_code = s.code
		for c in s.courses:
			course_code = c.code
			# if (course_code.split(':')[0] != '198'):
			# 	continue
			for p in c.prereqs:
				related_courses = p.related_courses()
				for rc in related_courses:
					if rc in edges and edges[rc] == course_code:
						continue
					else:
						g.add_edge(rc, course_code)
						e = g.get_edge(rc, course_code)
						e.attr['color']='#ffffff'
						e.attr['penwidth']='0.2'
						e.attr['arrowsize']='0.2'
						
						edges[rc] = course_code

						n1=g.get_node(rc)
						n1.attr['fillcolor']='%f 1.0 1.0' %(1.0 * float(rc.split(':')[0]) / 1000.0)
						n1.attr['style']='filled'
						n1.attr['color']='#ff000000'
						n1.attr['penwidth']='0.1'
						n1.attr['width']='0.2'

						n2=g.get_node(course_code)
						n2.attr['fillcolor']='%f 1.0 1.0' %(1.0 * float(course_code.split(':')[0]) / 1000.0)
						n2.attr['style']='filled'
						n2.attr['color']='#ff000000'
						n2.attr['penwidth']='0.1'
						n2.attr['width']='0.2'

	g.write('test-out.dot')

if __name__ == '__main__':
	data = None
	try:
		output = open('./temp.dump', 'r')
		data = pickle.load(output)
		output.close()
		pass
	except Exception, e:
		print "No saved data exists."
	if not data:
		subjects = downloadSubjectsAndParse()
		index = {}
		for s in subjects:
			subject_code = s.code
			for c in s.courses:
				course_code = c.code
				identifier = course_code
				index[identifier] = c

		data = {'subject': subjects, 'index': index}
		output = open('./temp.dump', 'w')
		pickle.dump(data, output)
		output.close()
	else:
		print "Load saved data."

	index = data['index']
	subjects = data['subject']
	prereq_graph(subjects)

	# while True:
	# 	temp = raw_input('enter option: ')
	# 	if temp[0] == 'f':
	# 		fulfillTest(index, temp.split(' ')[1])
	# 	elif temp[0] == 'm':
	# 		courseCodeList = temp[1:].split(',')
	# 		courseSet = set()
	# 		for code in courseCodeList:
	# 			courseSet.add(code.strip())
	# 		findAllMatchingClasses(subjects, courseSet)
	# 	elif temp[0] == 'e':
	# 		repl()
	# 	elif temp[0] == 'q':
	# 		break
	# 	elif temp[0] == 'g':
	# 		print graph_json(subjects)
	# 	elif temp[0] == 'd':
	# 		prereq_graph(subjects)
	# 		print "done creating graph"