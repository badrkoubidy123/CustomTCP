# any and all assistance with code provided by Python.org reference pages

import os
import sys
import socket
import threading

import random
import datetime

PACKET_MAXSIZE = 1024 # 1 kilobyte per packet
PACKET_SIZEINFOBYTES = 4 # 2 16-bit integers for packetNum and totalPackets
PACKET_DATABYTES = PACKET_MAXSIZE - PACKET_SIZEINFOBYTES

RECEIVE_HOST = "localhost"
RECEIVE_PORT = 1337

SEND_HOST = "localhost"
SEND_PORT = 1337

SOCK_RECEIVE = None
SOCK_SEND = None

SOCK_RECEIVE_TIMEOUT = 10.0
SOCK_SEND_TIMEOUT = 1.0 # 1 second to be safe, could make this lower later

MAX_SEND_RETRIES = 10 # if at first you don't succeed, try again

# these will be used to detect incoming file types
COMMON_FILE_BYTES = {}
COMMON_FILE_BYTES["bmp"] = b'\x42\x4d'
COMMON_FILE_BYTES["jpg"] = b'\xff\xd8'
COMMON_FILE_BYTES["png"] = b'\x89\x50\x4e\x47'
#COMMON_FILE_BYTES["mp4"] = b'\x\x'

RECEIVE_FILENAME = "received."
RECEIVE_FILENAME_EXTENSION = "FILE"

def determineFileExtension( packet ):
	if len( packet ) < 4:
		return "FILE"
		
	keys = list(COMMON_FILE_BYTES)
	for i in range( len(COMMON_FILE_BYTES) ):
		n = len( COMMON_FILE_BYTES[keys[i]] )
		if packet[:n] == COMMON_FILE_BYTES[keys[i]]:
			return keys[i]
			
	return "txt"

# setup the sockets with the supplied command-line parameters
# a GUI can be used for the next phase so this isn't so painful for the user
def initSockets():
	if len(sys.argv) < 5:
		print( "Usage: monolith.py [recv_host] [recv_port] [send_host] [send_port]" )
		sys.exit()
	else:
		global SOCK_RECEIVE, SOCK_SEND, RECEIVE_HOST, RECEIVE_PORT, SEND_HOST
		global SEND_PORT, SOCK_RECEIVE_TIMEOUT, SOCK_SEND_TIMEOUT
	
		if sys.argv[1] != "0":
			RECEIVE_HOST = sys.argv[1]
		if sys.argv[2] != "0":
			RECEIVE_PORT = int(sys.argv[2])
		if sys.argv[3] != "0":
			SEND_HOST = sys.argv[3]
		if sys.argv[4] != "0":
			SEND_PORT = int(sys.argv[4])
			
		SOCK_RECEIVE = socket.socket( socket.AF_INET, socket.SOCK_DGRAM )
		SOCK_RECEIVE.bind( (RECEIVE_HOST, RECEIVE_PORT) )
		SOCK_RECEIVE.settimeout( SOCK_RECEIVE_TIMEOUT )

		SOCK_SEND = socket.socket( socket.AF_INET, socket.SOCK_DGRAM )
		SOCK_SEND.settimeout( SOCK_SEND_TIMEOUT )

def receivePackets():
	global SOCK_RECEIVE, PACKET_MAXSIZE, RECEIVE_FILENAME_EXTENSION

	# wait for intial packet
	# this will be a daemon thread, it's okay to use while True because
	# this thread will be terminated by the OS if the user causes a 
	# KeyboardInterrupt exception on the main thread
	while True:
		try:
			initData, initAddress = SOCK_RECEIVE.recvfrom( PACKET_MAXSIZE )
		except socket.timeout:
			continue			
		
		initPacketNum = initData[0] | (initData[1]<<8)
		packetsToExpect = initData[2] | (initData[3]<<8)
		
		packetNumsReceived = []
		for i in range( packetsToExpect + 1 ):
			packetNumsReceived.append( False )
		packetNumsReceived[initPacketNum] = initData[4:]
		#don't forget to ACK the initial packet!
		SOCK_RECEIVE.sendto( b'ACK' + initPacketNum.to_bytes(2,byteorder='little'), initAddress ) 

		print( datetime.datetime.now().isoformat(), "Got initial packet, waiting for the rest!" )
		
		#once we have processed the initial packet, we can handle the rest
		restart = False
		while False in packetNumsReceived:
			try:
				data, address = SOCK_RECEIVE.recvfrom( PACKET_MAXSIZE )
			except socket.timeout:
				print( datetime.datetime.now().isoformat(), "Receive socket timed out, I'll wait for a new transmission" )
				restart = True
				break
				
			packetNum = data[0] | (data[1]<<8)
			packetNumsReceived[packetNum] = data[4:]
			
			SOCK_RECEIVE.sendto( b'ACK' + packetNum.to_bytes(2,byteorder='little'), initAddress )
		
		if restart:
			continue
			
		RECEIVE_FILENAME_EXTENSION = determineFileExtension( packetNumsReceived[0] )
		
		fout = open( RECEIVE_FILENAME + RECEIVE_FILENAME_EXTENSION, "wb" )
		for p in range( len(packetNumsReceived) ):
			fout.write( packetNumsReceived[p] )
		fout.close()
		RECEIVE_FILENAME_EXTENSION = "FILE"
		print( datetime.datetime.now().isoformat(), "Got all the packets!" )

# this function gets PACKET_DATABYTES number of bytes from the given
# filename at nPacket position offset from the file's beginning.
# since we are loading PACKET_DATABYTES bytes at a time, large files
# can still be sent without having to load all of the contents into memory
# TODO: implement similar behavior for handlePackets
def getFileBytes( filename, nPacket ):
	global PACKET_DATABYTES

	try:
		fin = open( filename, "rb" )
	except:
		print( "Error opening file" )
		return b''
	
	startPos = PACKET_DATABYTES * nPacket
	fin.seek( startPos, 0 )
	output = fin.read( PACKET_DATABYTES )
	return output

def getFileSize( filename ):
	try:
		fin = open( filename, "rb" )
	except:
		print( "Error opening file" )
		return -1
		
	fin.seek( 0, 2 )
	size = fin.tell()
	fin.close()
	
	return size
	
def sendPackets():
	global SOCK_SEND, SEND_HOST, SEND_PORT
	
	while True:
		print( "Enter the message to send:" )
		message = input()
		
		isFile = False
		
		# naively detect if the message is a filename
		# use commas/semicolons in string messages if you want multiple sentences
		if message.find( "." ) != -1:
			isFile = True
		
		if isFile:
			messageLength = getFileSize( message )
			print( "File length is", messageLength )
		else:
			messageLength = len(message)
			print( "Message length is", messageLength )
		
		# don't bother sending an empty message
		if messageLength > 0:
			numPackets = int( messageLength / PACKET_DATABYTES ) + 1
		else:
			continue
			
		print( "Packets needed:", numPackets )
		
		# for testing packets arriving out of order
		randomizePacketOrder = True
		
		if randomizePacketOrder:
			randomArray = []
			for i in range( numPackets ):
				randomArray.append( i )
			random.shuffle( randomArray )
		
		print( datetime.datetime.now().isoformat(), "Beginning packets transmission..." )
		
		# this is for reporting progress to the user
		targetNum = 20
		numParts = numPackets if numPackets < targetNum else targetNum
		partSize = int(numPackets / numParts)
		pieces = {}
		for i in range( numParts - 1 ):
			pieces[partSize*(i+1)] = int( 100 / numParts ) * ( i + 1 )
		
		for p in range( numPackets ):
			
			try:
				print( datetime.datetime.now().isoformat(), pieces[p], "percent transmitted" )
			except KeyError:
				pass
			except OverflowError:
				print( "Number was too big to print?" )
		
			curPacket = bytearray()
			
			if randomizePacketOrder:
				currentPacketNum = randomArray[p].to_bytes(2,byteorder='little')
			else:
				currentPacketNum = p.to_bytes(2,byteorder='little')
			
			totalPacketNum = (numPackets-1).to_bytes(2,byteorder='little')
			
			# here is where the packet is constructed as a bytearray			
			# prepend the bytes for packet num and total num of packets
			curPacket.append( currentPacketNum[0] )
			curPacket.append( currentPacketNum[1] )
			curPacket.append( totalPacketNum[0] )
			curPacket.append( totalPacketNum[1] )
			
			if isFile:			
				if randomizePacketOrder:
					packetBytes = getFileBytes( message, randomArray[p] )
				else:
					packetBytes = getFileBytes( message, p )
					
				for b in range( len(packetBytes) ):
					curPacket.append( packetBytes[b] )			
			else:
				start = p * PACKET_DATABYTES
				end = p * PACKET_DATABYTES + PACKET_DATABYTES - 1
				if ( messageLength < end ):
					end = messageLength
					
				for i in range( start, end ):
					curPacket.append( ord(message[i]) )	
			
			if tryPacketUntilSuccess( curPacket, MAX_SEND_RETRIES ) == False:
				print( datetime.datetime.now().isoformat(), "Couldn't send a packet, cancelling transmission..." )
				break
				
		print( datetime.datetime.now().isoformat(), "Transmission done" )
				
def tryPacketUntilSuccess( packet, max ):
	success = False
	while not success and max > 0:
		SOCK_SEND.sendto( packet, (SEND_HOST, SEND_PORT) )
		try:
			data, address = SOCK_SEND.recvfrom( 32 )
		except socket.timeout:
			print( datetime.datetime.now().isoformat(), "Fail#", MAX_SEND_RETRIES - max + 1, "retrying send..." )
			max -= 1
			if max == 0:
				return success
			continue
		#print( "Response:", data )
		success = True
		
	return success
			
# Here is the beginning of the program			
initSockets()
		
# Launch the listener in its own thread since it doesn't require user interaction	
receiveThread = threading.Thread( name="receive", target=receivePackets )
receiveThread.daemon = True
receiveThread.start()

# sendPackets is essentially the main function of this program
# it will keep prompting the user for data to send until the program is killed
sendPackets()