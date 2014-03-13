#!/usr/bin/env python
# -*- coding: utf8 -*-
# Get book information accroding to isbn

import sys

import requests
import json, yaml
import os
import mimetypes

import pgdb

def get_book_info_from_isbndb(isbn13):
	"""
	Get book information from isbndb, using canonical isbn13
	"""
	base_url = 'http://isbndb.com/api/v2/yaml/'
	api_key = 'EF2FC19S'
	full_url = base_url + api_key + '/book/%d' % isbn13

	ret = requests.get(full_url)
	data = yaml.load(ret.text)
	if data == {}: return None

	# Add author info
	result = {}
	author_list = [i['name'] for i in data['data'][0]['author_data']]
	authors = "{%s}" % ','.join(['"'+i+'"' for i in author_list])
	result['authors'] = authors
	# Add remained fields
	map_list = {'isbn10': ["'data'", "0", "'isbn10'"],
				'language': ["'data'", "0", "'language'"],
				'publishers': ["'data'", "0", "'publisher_name'"],
				'title': ["'data'", "0", "'title'"],
				'subtitle': ["'data'", "0", "'subtitle'"],
				'title_long': ["'data'", "0", "'title_long'"],
				'book_id': ["'data'", "0", "'book_id'"],
				'subject_id': ["'data'", "0", "'subject_ids'", 0]};
	for k in map_list.keys():
		try :
			index = ''.join(['['+i+']' for i in map_list[k]])
			exec """result[k] = data%s""" % index
		except (TypeError, KeyError):
			pass
	
	return result

#print get_book_info_from_isbndb(9782705656751)

def get_book_info_from_openlib(isbn13):
	"""
	Get book information from Open Libary, according to canonical isbn13.
	"""
	base_url = 'http://openlibrary.org/api/books'
	query_string = '?bibkeys=ISBN:%d&jscmd=details&format=json' % isbn13
	full_url = base_url + query_string

	ret = requests.get(full_url)
	data = json.loads(ret.text)
	if data == {} : return None
	data = data['ISBN:%d' % isbn13]

	result = {}
	# Add author info
	author_list = [i['name'] for i in data['details']['authors']]
	authors = "{%s}" % ','.join(['"'+i+'"' for i in author_list])
	result['authors'] = authors
	# Add remined field
	map_list = {'isbn10': ["'details'", "'isbn_10'", "0"],
				'thumbnail_url': ["'thumbnail_url'"],
				'latest_version': ["'details'", "'latest_version'"],
				'pages': ["'details'", "'number_of_pages'"],
				'publish_date': ["'details'", "'publish_date'"],
				'publishers': ["'details'", "'publishers'", "0"],
				'version': ["'details'", "'revision'"],
				'title': ["'details'", "'title'"],
				'subtitle' : ["'details'", "'subtitle'"] }
	for k in map_list.keys():
		try :
			index = ''.join(['['+i+']' for i in map_list[k]])
			exec """result[k] = data%s""" % index
		except (TypeError, KeyError):
			pass
	
	return result

#print get_book_info_from_openlib(9780201142365)

def add_book_info(isbn13, book_info):
	"""
	Add book information to PostgreSQL server, 
	isbn13 is canonical form of 13-digit ISBN number;
	book_info is got through methods listed above.
	"""
	if book_info == None: return False

	session = pgdb.connect(user='hawk', password='hawk', database='dist')
	cursor = session.cursor()

	# Add book record if ISBN13(primary key) does not exist.
	sql = '''SELECT book_info FROM book_info WHERE isbn13=%d''' % isbn13
	cursor.execute(sql)
	f = cursor.fetchall()
	if f == [] :
		cursor.execute('''INSERT INTO book_info(isbn13) 
				VALUES ('%d')''' % isbn13)

	# Add book info
	for i in book_info.keys():
		sql = u'''UPDATE book_info SET %s='%s'
				WHERE isbn13='%s' ''' % (i, book_info[i], isbn13)
		cursor.execute(sql)

	cursor.close()
	session.commit()
	session.close()

	print "Done."

#isbn13 = 9782705656751
#add_book_info(isbn13, get_book_info_from_isbndb(isbn13))
#isbn13 = 9780201142365
#add_book_info(isbn13, get_book_info_from_openlib(isbn13))

def isbn10to13(isbn10):
	"""
	Convert isbn10 to isbn13 canonical form.
	"""
	# string to integer
	isbn10 = int(isbn10[0:9])

	# calculate checksum
	std = isbn10+978*(10**9)
	digits = [std/10**i - 10*(std/(10**(i+1))) for i in range(0,12)]
	digits.reverse()
	weight = [digits[i]*(1 if i%2==0 else 3) for i in range(0,len(digits))]
	totals = sum(weight)
	reminder = totals - 10*(totals/10)
	checked = 0 if reminder==10 else 10-reminder
	digits.append(checked)
	isbn13 = sum([digits[12-i]*10**i for i in range(0,13)])

	return isbn13

def ensure_isbn13(isbn):
	"""
	Ensure isbn13 canonical form.
	"""
	try :
		if type(isbn) == unicode or type(isbn) == str:
			isbn = ''.join(isbn.split('-'))
			if len(isbn) == 10 : 
				isbn = isbn10to13(isbn)
			isbn = int(isbn)
	except: # parsing failed
		return False
	if type(isbn) != int: return False

	return isbn

def get_book_data(path, isbn):

	isbn13 = ensure_isbn13(isbn)

	uri = os.path.abspath(os.path.expanduser(path))

	if not os.path.isfile(uri):
		return False

	name = os.path.basename(uri)
	size = os.path.getsize(uri)
	mime = mimetypes.guess_type(uri)[0]
	mime = mime if mimetypes != None else ''

	data = {'isbn':isbn13, 'name':name, 'mime':mime, 'size':size, 'uri':uri}
	return data

#isbn = '123456789X'
#print get_book_data('~/file/html/www.unicode.org/CodeCharts.pdf', isbn)

def add_book_data(path, isbn):
	"""
	Add local book data to PostgreSQL server.
	"""
	data = get_book_data(path=path, isbn=isbn)

	if not data : return False

	session = pgdb.connect(user='hawk', password='hawk', database='dist')
	cursor = session.cursor()

	# what if previous record already exists?

	sql = '''INSERT INTO book_data(isbn,name,mime,size,uri,data)
		VALUES(%(isbn)d, '%(name)s', '%(mime)s',
		%(size)d, '%(uri)s', lo_import('%(uri)s') )''' % data
	try : 
		cursor.execute(sql)
	except pgdb.DatabaseError:
		return False

	cursor.close()
	session.commit()
	session.close()

	print "Done"
	return True

isbn= sys.argv[1]
print get_book_info_from_openlib(ensure_isbn13(isbn))
#print add_book_data('~/file/html/www.unicode.org/CodeCharts.pdf', isbn)
