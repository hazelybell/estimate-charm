// JavaScript Document

var dropDownTimeOut = 0;

dropDownBg = new Image(); 
dropDownBg.src="images/bg-dropdown.png"; 

$(document).ready(function(){
	initDropDown();
});

function initDropDown() {
	$("#navigation-drop-down").mouseover(function(){
      dropDownIn();
    })
	$("#navigation-drop-down").mouseout(function(){
      dropDownOut();
    })	
}

function dropDownOut() {
	dropDownTimeOut = setTimeout('$("#navigation-drop-down").removeClass("menu");', 400);
}

function dropDownIn() {
	clearTimeout(dropDownTimeOut);
	$("#navigation-drop-down").addClass("menu");
}