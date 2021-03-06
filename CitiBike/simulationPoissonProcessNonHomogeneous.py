"""
Queuing simulation based on New York City's Bike system,
in which system users may remove an available bike from
a station at one location within the city, and ride it
to a station with an available dock in some other location
within the city.

The overall number negatively affected trips is computed.

"""

import numpy as np
from math import *
from geopy.distance import vincenty
import json
from numpy import linalg as LA
from scipy.stats import poisson
from scipy.stats import rv_discrete
import os
from scipy.sparse import csr_matrix as csr



distancesBikeStations=np.loadtxt("distanceBikeStations.txt")
nBikes=6000
"""distancesBikeStations (numpy array): matrix with the entry (i,j) equal to
                                        the distrance between the ith station
                                        and jth station.
   nBikes (int): overall number of bikes.
"""



def PoissonProcess(T,lamb,A,N,randst,nStations=329):
    """
    Simulate the poisson process N(T,(i,j)) where (i,j) is in the set A,
    and N(T,(i,j)) is the poisson process related to the pair (i,j);
    and A is a subset of stations. Return the number of times generated.

    Args:
        T (int): Final time of the simulation.
        A (List[Tuple(int,int)]): Subset of pair of bike stations. 
        N (int): N(T,A)=sum(i,j in A) N(T,(i,j)).
        lamb (List[numpy array]): List with the parameters
                                  of the Poisson processes N(T,(i,j)), 
                                  (i.e. jth entry of lamb is the Poisson process
                                   with parameter lamb[0][0,j] between stations
                                   lamb[0][1,j] and lamb[0][2,j]).
        nStations (int): Number of bike stations.
        
    Returns:
        Tuple composed by:
          List[List[List[Tuple(int,int)],List[float]]]:
                                        List with the arrival
                                        times for each set A: (A[i],Times).
          int: Overall number of arrivals.
    """
    n=len(A) 
    prob=np.zeros(n)
    lambSum=(np.sum(lamb[0][0,:]))
    nElements=len(lamb[0][0,:])
    for j in xrange(nElements):
        prob[lamb[0][2,j]+(lamb[0][1,j])*nStations]=(float(lamb[0][0,j])/(lambSum))
    X=randst.multinomial(N,prob,size=1)[0]
    nArrivals=np.sum(X)
    TIME=[]
    for i in xrange(n):
        if (X[i]>0):
            unif=randst.uniform(0,1,X[i])
            temp=np.sort(float(T)*unif)
            TIME.append([A[i],temp])
    return TIME,nArrivals



def startInitialConfiguration (X,m,cluster,bikeData,files=False,nStations=329):
    """
    Set the initial configuration of the citibike problem. Returns a
    matrix with the number of docks and bikes available.
    
    Args:
        -X (numpy array): Vector with the initial configuration of bikes.
        -m (int): Number of clusters of the bike stations.
        -cluster (List[List[List[int,float,float]]]):
                                Contains the clusters of the bike stations
                                with their ids, and geographic coordinates.
        -bikeData (numpy array): Matrix with the ID, numberDocks, Latitute,
                                 and longitude of each bike station.
        -files (bool): True if we want to save the initial configuration;
                False otherwise.

    Returns:
        numpy array: nStations-by-2 matrix with the number of docks and
                     bikes available at each bike station.
    """
    A=np.zeros((nStations,2))
    A[:,0]=bikeData[:,2]
    if files:
      f= open(str(m)+"-initialConfiguration.txt", 'w')
      f.write("docks"+","+"bickes"+","+"ID"+","+"total"+","+
              "bikes/total"+","+"latitude"+","+"longitude"+
              ","+"streets")
    for i in range(m):
        temp=cluster[i]
        resT=X[i]
        inds=np.array([a[0] for a in temp])
        indx=np.where(A[inds,0]>0)[0]
        nElm=len(indx)
        indx2=inds[indx]
        while (resT>0):
            setBikes=int(resT/nElm)
            if setBikes==0:
                A[indx2[0:resT],1]+=1
                A[indx2[0:resT],0]-=1
                break
            index2=np.where((A[indx2,0]-setBikes)<0)[0]
                #indices where no all bikes can be placed
            index3=set(range(0,nElm))-set(index2)
                #indices where all bikes can be placed
            index3=np.array(list(index3))
            tempA=A[indx2[index2],0]
            A[indx2[index2],1]+=tempA
            A[indx2[index2],0]-=tempA #docks
            A[indx2[index3],1]+=setBikes
            A[indx2[index3],0]-=setBikes
            res2=np.sum(-A[indx2[index2],1]+setBikes)
            resT=(resT%nElm)+res2
            indx=np.where(A[inds,0]>0)[0]
            indx2=inds[indx]
            nElm=len(indx)
    return A



def findBikeStation(state,currentBikeStation):
    """
    Find the closest bike station to currentBikeStation with available docks.
    
    Args:
        state (numpy array): Matrix with the number of available docks
                             of all the bike stations.
        currentBikeStation (int): index of the current bike station.
    
    Returns:
        int: Index of the the closest bike station to currentBikeStation
             with available docks.
    """
    dist=distancesBikeStations[currentBikeStation,:]
    sort=[i[0] for i in sorted(enumerate(dist), key=lambda x:x[1])]
    k=1
    while True:
        ind=sort[k]
        if state[ind,0]>0:
            return ind
        else:
            k+=1
    return 0



def negativelyAffectedTrips (T,N,X,m,cluster,bikeData,parLambda,nDays,A,
                            poissonArray,timesArray,ind=None,randomSeed=None,
                            nStations=329):
    """
    Counts the number of negatively affected trips.
    We divide the bike stations in m groups according to K-means algorithm.
    The bikes are distributed uniformly in each group.
    
    Args:
        T (int): Duration of the simulation in hours (it always starts at 7:00am).
        N (numpy array): Vector N(T,A_{i}).
        X (numpy array): Vector with the initial configuration of the bikes.
        m (int): Number of groups formed with the bike stations.
        cluster (List[List[List[int,float,float]]]):
                            Contains the clusters of the bike stations
                            with their ids, and geographic coordinates.
        bikeData (numpy array): Matrix with the ID, numberDocks, Latitute,
                                and longitude of each bike station.
        parLambda (numpy array) : Vector with the parameters of the
                                  Poisson processes  N(T,A_{i}).
        nDays: Number of different days considered in the simulation (i.e. 365).
        A (List[List[Tuple(int,int)]]): List with subsets of pair of bike stations.
                lamb (List[numpy array]): List with the parameters
                                  of the Poisson processes N(T,(i,j)), 
                                  (i.e. jth entry of lamb is the Poisson process
                                   with parameter lamb[0][0,j] between stations
                                   lamb[0][1,j] and lamb[0][2,j]).
        poissonArray (List[List[numpy array]]):
            List with the parameters of the Poisson processes N(T,(i,j)), where 
            the jth entry of poissonArray are the parameters of the Poissons
            processes of day j between each pair of bike stations.
            (i.e., the parameter of the Poisson process on day j between stations
            lamb[j][0][1,l] and lamb[j][0][2,l] is lamb[j][0][0,l]. This is a
            sparse representation of the original matrix, and so if a pair of
            stations doesn't appear in the last list, its PP has parameter zero.
        timesArray (List[List[numpy array]]):
            Similar tan poissonArray, but with the mean times of traveling between
            the stations.
        ind (int or None): Day of the year when the simulation is run.
        randomSeed (int): Random seed.
        nStations (int): Number of bike stations.
        
    Returns:
        int: Overall number of negatively affected tripes multiplied by -1.
    """
    if randomSeed is not None:
        randst = np.random.mtrand.RandomState(randomSeed)
    else:
        randst=np.random

    if ind is None:
        probs=poisson.pmf(int(N[0]),mu=np.array(parLambda))
        probs=probs/np.sum(probs)
        ind=randst.choice(range(nDays),size=1,p=probs)
        
    exponentialTimes=timesArray[ind][0]
    exponentialTimes2=np.zeros((nStations,nStations))
    nExp=len(exponentialTimes[0,:])
    for i in range(nExp):
        t1=exponentialTimes[1,i]
        t2=exponentialTimes[2,i]
        exponentialTimes2[t1,t2]=exponentialTimes[0,i]
    poissonParam=poissonArray[ind]

    unHappy=0
    state=startInitialConfiguration(X,m,cluster,bikeData,nDays)

    nSets=1
    times=[]
    nTimes=0
    for i in range(nSets):
        temp=PoissonProcess(T,poissonParam,A[i],N[i],randst)

        nTimes+=temp[1]
        times.extend(temp[0])

    Times=np.zeros((nTimes,3))
    k=0
    for i in range(len(times)):
        for j in range(len(times[i][1])):
            Times[k,0]=times[i][1][j] #arrival times
            Times[k,1]=times[i][0][0] #station i
            Times[k,2]=times[i][0][1] #station j
            k+=1
    Times=Times[Times[:,0].argsort()]
    currentTime=0
    dropTimes=[]
    for i in xrange(nTimes):
        currentTime=Times[i,0]
        while (dropTimes and currentTime>dropTimes[0][0]):
            if state[dropTimes[0][1],0]>0:
                state[dropTimes[0][1],0]=state[dropTimes[0][1],0]-1
                state[dropTimes[0][1],1]+=1
                dropTimes.pop(0)
            else:
                unHappy+=1
                j=findBikeStation(state,dropTimes[0][1])
                state[j,0]=state[j,0]-1
                state[j,1]=state[j,1]+1
                dropTimes.pop(0)
        bikePickUp=Times[i,1]
        bikeDrop=Times[i,2]

        if state[bikePickUp,1]==0:
            unHappy+=1
            continue
        indi=exponentialTimes[1,]
        timeUsed=randst.exponential(exponentialTimes2[bikePickUp,bikeDrop])
        dropTimes.append((currentTime+timeUsed,bikeDrop))
        dropTimes=sorted(dropTimes, key=lambda x:x[0])
        state[bikePickUp,1]=state[bikePickUp,1]-1
        state[bikePickUp,0]=state[bikePickUp,0]+1
    return -unHappy
