#include <iostream>
#include <vector>
#include <set>
#include <cstdlib>
#include "Align.h"

Align::Align(std::vector<std::string> A,size_t x, size_t y){
  len_x = x;
  len_y = y;
  std::set<size_t> myset;
  for (size_t i=0; i<len_x; i++) x2y.push_back(myset);
  for (size_t i=0; i<len_y; i++) y2x.push_back(myset);

  for (size_t i=0; i<A.size(); i++){
    size_t pos = A[i].find('-');
    if (pos == std::string::npos){
      std::cerr << "error: bad alignment format: "<< A[i] << std::endl;
      exit(1);
    }
    size_t s = std::atoi(A[i].substr(0,pos).c_str());
    size_t t = std::atoi(A[i].substr(pos+1).c_str());
    x2y[s].insert(t);
    y2x[t].insert(s);
    ali_xy.push_back(std::make_pair(s,t));
  }
  return;
}

std::vector<std::pair<std::set<size_t>, std::set<size_t> > > Align::Groups(bool side_is_src, bool consecutive){ 
  std::vector<std::pair<std::set<size_t>, std::set<size_t> > > groups;
  size_t len_s, len_t;
  if (side_is_src){
    len_s = len_x;
    len_t = len_y;
  }
  else{
    len_t = len_x;
    len_s = len_y;
  }

  std::set<size_t> processed_s;
  std::set<size_t> processed_t;
  for (size_t s=0; s<len_s; s++){
    if (processed_s.find(s) != processed_s.end()){ //already processed
      continue;
    }
    std::set<size_t> news;
    std::set<size_t> newt;
    news.insert(s);
    if (side_is_src) Align::aligned_to_s(news,newt,consecutive,x2y,y2x);
    else Align::aligned_to_s(news,newt,consecutive,y2x,x2y);
    for (std::set<size_t>::iterator it=news.begin(); it!=news.end(); it++){
      if (processed_s.find(*it) != processed_s.end()){
	std::cerr << "error: source word processed twice!"<< std::endl;
	exit(1);	
      }
      processed_s.insert(*it);
    }
    for (std::set<size_t>::iterator it=newt.begin(); it!=newt.end(); it++){
      if (processed_t.find(*it) != processed_t.end()){
	std::cerr << "error: target word processed twice!"<< std::endl;
	exit(1);	
      }
      processed_t.insert(*it);
    }
    if (side_is_src) groups.push_back(std::make_pair(news,newt));    
    else groups.push_back(std::make_pair(newt,news));    
  }
  //add all words t that are not processed
  for (size_t t=0; t<len_t; t++){
    if (processed_t.find(t) == processed_t.end()){
      std::set<size_t> news; //empty
      std::set<size_t> newt;
      newt.insert(t);
      if (side_is_src) groups.push_back(std::make_pair(news,newt));
      else groups.push_back(std::make_pair(newt,news));
    }
  }
  return groups;
}

void Align::aligned_to_s(std::set<size_t>& news, std::set<size_t>& newt, bool consecutive, std::vector<std::set<size_t> >& s2t, std::vector<std::set<size_t> >& t2s){
  size_t total = 0;
  while (true){
    for (std::set<size_t>::iterator it_s=news.begin(); it_s!=news.end(); it_s++){
      for (std::set<size_t>::iterator it_t=s2t[*it_s].begin(); it_t!=s2t[*it_s].end(); it_t++){
	newt.insert(*it_t);
      }
    }
    if (news.size() + newt.size() == total) return;
    total = news.size() + newt.size();

    for (std::set<size_t>::iterator it_t=newt.begin(); it_t!=newt.end(); it_t++){
      for (std::set<size_t>::iterator it_s=t2s[*it_t].begin(); it_s!=t2s[*it_t].end(); it_s++){
	news.insert(*it_s);
      }
    }
    if (consecutive && news.size()){
      size_t min = *(--news.rend());
      size_t max = *news.rbegin(); 
      for (size_t s=min; s<=max; s++){
	news.insert(s);
      }
    }    
    if (news.size() + newt.size() == total) return;
    total = news.size() + newt.size();
  }
}


