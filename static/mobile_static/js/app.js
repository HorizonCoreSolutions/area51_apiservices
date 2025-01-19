/******/ (function(modules) { // webpackBootstrap
/******/ 	// The module cache
/******/ 	var installedModules = {};
/******/
/******/ 	// The require function
/******/ 	function __webpack_require__(moduleId) {
/******/
/******/ 		// Check if module is in cache
/******/ 		if(installedModules[moduleId]) {
/******/ 			return installedModules[moduleId].exports;
/******/ 		}
/******/ 		// Create a new module (and put it into the cache)
/******/ 		var module = installedModules[moduleId] = {
/******/ 			i: moduleId,
/******/ 			l: false,
/******/ 			exports: {}
/******/ 		};
/******/
/******/ 		// Execute the module function
/******/ 		modules[moduleId].call(module.exports, module, module.exports, __webpack_require__);
/******/
/******/ 		// Flag the module as loaded
/******/ 		module.l = true;
/******/
/******/ 		// Return the exports of the module
/******/ 		return module.exports;
/******/ 	}
/******/
/******/
/******/ 	// expose the modules object (__webpack_modules__)
/******/ 	__webpack_require__.m = modules;
/******/
/******/ 	// expose the module cache
/******/ 	__webpack_require__.c = installedModules;
/******/
/******/ 	// define getter function for harmony exports
/******/ 	__webpack_require__.d = function(exports, name, getter) {
/******/ 		if(!__webpack_require__.o(exports, name)) {
/******/ 			Object.defineProperty(exports, name, { enumerable: true, get: getter });
/******/ 		}
/******/ 	};
/******/
/******/ 	// define __esModule on exports
/******/ 	__webpack_require__.r = function(exports) {
/******/ 		if(typeof Symbol !== 'undefined' && Symbol.toStringTag) {
/******/ 			Object.defineProperty(exports, Symbol.toStringTag, { value: 'Module' });
/******/ 		}
/******/ 		Object.defineProperty(exports, '__esModule', { value: true });
/******/ 	};
/******/
/******/ 	// create a fake namespace object
/******/ 	// mode & 1: value is a module id, require it
/******/ 	// mode & 2: merge all properties of value into the ns
/******/ 	// mode & 4: return value when already ns object
/******/ 	// mode & 8|1: behave like require
/******/ 	__webpack_require__.t = function(value, mode) {
/******/ 		if(mode & 1) value = __webpack_require__(value);
/******/ 		if(mode & 8) return value;
/******/ 		if((mode & 4) && typeof value === 'object' && value && value.__esModule) return value;
/******/ 		var ns = Object.create(null);
/******/ 		__webpack_require__.r(ns);
/******/ 		Object.defineProperty(ns, 'default', { enumerable: true, value: value });
/******/ 		if(mode & 2 && typeof value != 'string') for(var key in value) __webpack_require__.d(ns, key, function(key) { return value[key]; }.bind(null, key));
/******/ 		return ns;
/******/ 	};
/******/
/******/ 	// getDefaultExport function for compatibility with non-harmony modules
/******/ 	__webpack_require__.n = function(module) {
/******/ 		var getter = module && module.__esModule ?
/******/ 			function getDefault() { return module['default']; } :
/******/ 			function getModuleExports() { return module; };
/******/ 		__webpack_require__.d(getter, 'a', getter);
/******/ 		return getter;
/******/ 	};
/******/
/******/ 	// Object.prototype.hasOwnProperty.call
/******/ 	__webpack_require__.o = function(object, property) { return Object.prototype.hasOwnProperty.call(object, property); };
/******/
/******/ 	// __webpack_public_path__
/******/ 	__webpack_require__.p = "/";
/******/
/******/
/******/ 	// Load entry module and return exports
/******/ 	return __webpack_require__(__webpack_require__.s = 0);
/******/ })
/************************************************************************/
/******/ ({

/***/ "./resources/js/app.js":
/*!*****************************!*\
  !*** ./resources/js/app.js ***!
  \*****************************/
/*! no static exports found */
/***/ (function(module, exports, __webpack_require__) {

/**
 * First we will load all of this project's JavaScript dependencies which
 * includes Vue and other libraries. It is a great starting point when
 * building robust, powerful web applications using Vue and Laravel.
 */
__webpack_require__(/*! ./mg/MG */ "./resources/js/mg/MG.js"); // require('./bootstrap');
// window.Vue = require('vue');

/**
 * The following block of code may be used to automatically register your
 * Vue components. It will recursively scan this directory for the Vue
 * components and automatically register them with their "basename".
 *
 * Eg. ./components/ExampleComponent.vue -> <example-component></example-component>
 */
// const files = require.context('./', true, /\.vue$/i)
// files.keys().map(key => Vue.component(key.split('/').pop().split('.')[0], files(key).default))
// Vue.component('example-component', require('./components/ExampleComponent.vue').default);

/**
 * Next, we will create a fresh Vue application instance and attach it to
 * the page. Then, you may begin adding components to this application
 * or customize the JavaScript scaffolding to fit your unique needs.
 */
// const app = new Vue({
//     el: '#app'
// });

/***/ }),

/***/ "./resources/js/mg/DatePicker.js":
/*!***************************************!*\
  !*** ./resources/js/mg/DatePicker.js ***!
  \***************************************/
/*! no static exports found */
/***/ (function(module, exports) {

MG.DatePicker = function () {
  function DatePicker(options) {
    this.settings = {
      id: '#search-date-from',
      dateFormat: "yy-mm-dd"
    };
    jQuery.extend(this.settings, options);
    var scope = this;
    this.events = new MG.EventHandler();
    $(scope.settings.id).datepicker({
      defaultDate: "+1w",
      changeMonth: true,
      numberOfMonths: 1,
      dateFormat: scope.settings.dateFormat
    });
  }

  ;
  DatePicker.prototype = {
    constructor: DatePicker
  };
  return DatePicker;
}();

/***/ }),

/***/ "./resources/js/mg/DateRangePicker.js":
/*!********************************************!*\
  !*** ./resources/js/mg/DateRangePicker.js ***!
  \********************************************/
/*! no static exports found */
/***/ (function(module, exports) {

MG.DateRangePicker = function () {
  function DateRangePicker(options) {
    this.settings = {
      from: {
        id: '#search-date-update-from',
        format: "Y-m-d H:i",
        defaultDate: new Date(),
        value: ''
      },
      to: {
        id: '#search-date-update-to',
        format: "Y-m-d H:i",
        defaultDate: new Date(),
        value: ''
      }
    };
    jQuery.extend(this.settings, options);
    var scope = this;
    this.events = new MG.EventHandler();
    var from = $(scope.settings.from.id).datetimepicker({
      format: scope.settings.from.format,
      defaultDate: scope.settings.from.defaultDate,
      value: scope.settings.from.value,
      mask: true,
      onShow: function onShow(ct) {
        this.setOptions({
          maxDate: jQuery(scope.settings.to.id).val() ? jQuery(scope.settings.to.id).val() : false
        });
      }
    });
    to = $(scope.settings.to.id).datetimepicker({
      format: scope.settings.to.format,
      defaultDate: scope.settings.to.defaultDate,
      value: scope.settings.to.value,
      mask: true,
      onShow: function onShow(ct) {
        this.setOptions({
          minDate: jQuery(scope.settings.from.id).val() ? jQuery(scope.settings.from.id).val() : false
        });
      }
    });
  }

  ;
  DateRangePicker.prototype = {
    constructor: DateRangePicker
  };
  return DateRangePicker;
}();

/***/ }),

/***/ "./resources/js/mg/EventHandler.js":
/*!*****************************************!*\
  !*** ./resources/js/mg/EventHandler.js ***!
  \*****************************************/
/*! no static exports found */
/***/ (function(module, exports) {

//EventHandler
MG.EventHandler = function () {
  function EventHandler() {
    var _triggers = {};

    this.on = function (event, callback) {
      if (!_triggers[event]) _triggers[event] = [];

      _triggers[event].push(callback);
    };

    this.triggerHandler = function (event, params) {
      if (_triggers[event]) {
        for (i in _triggers[event]) {
          _triggers[event][i](params);
        }
      }
    };
  }

  ;
  EventHandler.prototype = {
    constructor: EventHandler
  };
  return EventHandler;
}();

/***/ }),

/***/ "./resources/js/mg/MG.js":
/*!*******************************!*\
  !*** ./resources/js/mg/MG.js ***!
  \*******************************/
/*! no static exports found */
/***/ (function(module, exports, __webpack_require__) {

MG = {
  isEmpty: function isEmpty(str) {
    return !str || !/[^\s]+/.test(str);
  },
  fixIcon: function fixIcon(icon) {
    if (icon) {
      icon = icon.replace("fa-volume-control-phone", "fa-phone");
      icon = icon.replace("fa-envelope-o", "fa-envelope");
      icon = icon.replace("fa-envelope-o", "fa-envelope");
      icon = icon.replace("fa-envelope-o", "fa-envelope");
    } else {
      icon = "";
    }

    return icon;
  },
  cloneObject: function cloneObject(src) {
    return Object.assign({}, src);
  },
  getContentHeight: function getContentHeight() {
    var screen = $.mobile.getScreenHeight(),
        header = $(".ui-header").hasClass("ui-header-fixed") ? $(".ui-header").outerHeight() - 1 : $(".ui-header").outerHeight(),
        footer = $(".ui-footer").hasClass("ui-footer-fixed") ? $(".ui-footer").outerHeight() - 1 : $(".ui-footer").outerHeight(),
        contentCurrent = $(".ui-content").outerHeight() - $(".ui-content").height(),
        contentHeight = screen - header - footer - contentCurrent;
    return contentHeight;
  },
  scroll: function scroll(e) {
    $("body").scroll(function (o) {
      if (o.offsetHeight + o.scrollTop == o.scrollHeight) {
        alert("End");
      }
    });
  },
  currencyFormatEuro: function currencyFormatEuro(num) {
    return "€ " + Number(num).toFixed(2) // always two decimal digits
    .replace(".", ",") // replace decimal point character with ,
    .replace(/(\d)(?=(\d{3})+(?!\d))/g, "$1."); // use . as a separator
  }
};

Object.prototype.hasOwnProperty = function (property) {
  return this[property] !== undefined;
};

__webpack_require__(/*! ./EventHandler */ "./resources/js/mg/EventHandler.js");

__webpack_require__(/*! ./Row */ "./resources/js/mg/Row.js"); //require('./SelectFilterable');


__webpack_require__(/*! ./PageScroller */ "./resources/js/mg/PageScroller.js");

__webpack_require__(/*! ./MultipleAutocomplete */ "./resources/js/mg/MultipleAutocomplete.js");

__webpack_require__(/*! ./DateRangePicker */ "./resources/js/mg/DateRangePicker.js");

__webpack_require__(/*! ./DatePicker */ "./resources/js/mg/DatePicker.js");

/***/ }),

/***/ "./resources/js/mg/MultipleAutocomplete.js":
/*!*************************************************!*\
  !*** ./resources/js/mg/MultipleAutocomplete.js ***!
  \*************************************************/
/*! no static exports found */
/***/ (function(module, exports) {

//https://dragonofmercy.github.io/Tokenize2/events.html
MG.MultipleAutocomplete = function () {
  function MultipleAutocomplete(options) {
    this.settings = {
      id: "#multiple-autocomplete",
      valueKey: "id",
      nameKey: "name",
      data: [{
        id: 1,
        name: "test"
      }, {
        id: 2,
        name: "test2"
      }],
      ajaxSettings: {
        url: "{{URL::to('terminals')}}" + "/lookup",
        type: "get",
        data: {
          _token: "{{ csrf_token() }}"
        }
      },
      ajaxOnAwake: true,
      placeholder: false,
      tokensMaxItems: false
    };
    jQuery.extend(this.settings, options);
    var scope = this;
    if (!scope.element().length) return; //scope.setData(scope.settings.data);

    if (scope.settings.ajaxOnAwake) {
      scope.ajaxCall();
    } else {
      scope.setData(scope.settings.data);
      scope.selectItems(scope.settings.selectedItems);
    } // scope
    //     .element()
    //     .tokenize2()
    //     .on("click", function() {
    //         scope
    //             .element()
    //             .tokenize2()
    //             .trigger("tokenize:search", "");
    //     });

  }

  MultipleAutocomplete.prototype = {
    constructor: MultipleAutocomplete,
    element: function element() {
      return $(this.settings.id);
    },
    clear: function clear() {
      this.tokenize.trigger("tokenize:clear");
    },
    setData: function setData(data) {
      var scope = this;
      scope.element().html("");
      var html = "";

      for (var key in data) {
        var item = data[key];
        html += "<option value='" + item[scope.settings.valueKey] + "'>" + item[scope.settings.nameKey] + "</option>";
      }

      scope.element().append(html);
      scope.tokenize = scope.element().tokenize2({
        placeholder: scope.settings.placeholder,
        tokensMaxItems: scope.settings.tokensMaxItems
      });
      scope.tokenize.trigger("tokenize:remap");
      scope.selectItems(scope.settings.selectedItems);
      console.log(scope.tokenize.container);
      scope.tokenize.container.on("click", function () {
        scope.tokenize.trigger("tokenize:search", "");
      });
    },
    selectItems: function selectItems(values) {
      var scope = this;
      $.each(values.split(","), function (i, e) {
        scope.element().find("option[value='" + e + "']").prop("selected", true);
      });
      scope.tokenize.trigger("tokenize:remap");
    },
    ajaxCall: function ajaxCall() {
      var scope = this;
      $.ajax(this.settings.ajaxSettings).then(function (response) {
        scope.setData(response); //[{id:11, name:"test"},{id:12, name:"ttet"}]
      });
    },
    removeFromArray: function removeFromArray(original, remove) {
      return original.filter(function (value) {
        return !remove.includes(value);
      });
    }
  };
  return MultipleAutocomplete;
}();

/***/ }),

/***/ "./resources/js/mg/PageScroller.js":
/*!*****************************************!*\
  !*** ./resources/js/mg/PageScroller.js ***!
  \*****************************************/
/*! no static exports found */
/***/ (function(module, exports) {

MG.PageScroller = function () {
  function PageScroller(options) {
    this.settings = {
      tableId: "#table-id",
      searchOnAwake: true,
      search: {
        ajax: {
          getSettings: function getSettings() {
            return {
              type: "POST",
              url: "{{URL::to('/customers/search')}}",
              dataType: "json",
              beforeSend: function beforeSend(xhr) {
                var token = $('meta[name="csrf_token"]').attr("content");

                if (token) {
                  return xhr.setRequestHeader("X-CSRF-TOKEN", token);
                }
              },
              data: {
                searchName: $("#search-name").val(),
                searchNr: $("#search-nr").val(),
                searchDesc: $("#search-desc").val(),
                skip: $("li", "#list").length,
                take: 10
              }
            };
          }
        }
      },
      delete: {
        ajax: {
          getSettings: function getSettings(id) {
            return {
              url: "{{URL::to('customers')}}" + "/" + id,
              type: "post",
              data: {
                _method: "delete",
                _token: "{{ csrf_token() }}"
              },
              success: function success(result) {
                $("#li-" + id).remove();
              }
            };
          }
        }
      },
      edit: {
        geUrl: function geUrl(id) {
          return "{{URL::to('customers')}}" + "/" + id + "/edit";
        }
      }
    };
    jQuery.extend(this.settings, options);
    this.events = new MG.EventHandler();
    this.row = new MG.Row({
      id: this.settings.tableId
    });
  }

  PageScroller.prototype = {
    constructor: PageScroller,
    search: function search() {
      var scope = this;
      scope.events.triggerHandler("search_start");
      $.ajax(scope.settings.search.ajax.getSettings()).then(function (response) {
        scope.events.triggerHandler("search_response", response);
        scope.events.triggerHandler("search_end");
        scope.onAfterAddListItems(response);
      });
    },
    addMore: function addMore() {
      var scope = this;
      scope.events.triggerHandler("addMore_start");
      $.ajax(scope.settings.search.ajax.getSettings()).then(function (response) {
        scope.events.triggerHandler("addMore_response", response);
        scope.events.triggerHandler("addMore_end");
        scope.onAfterAddListItems(response);
      });
    },
    init: function init() {
      var scope = this;
      if (scope.settings.searchOnAwake) scope.search();
      scope.events.triggerHandler("load");
      scope.startRender();
    },
    onAfterAddListItems: function onAfterAddListItems(response) {
      var scope = this;
      scope.events.triggerHandler("afterAddListItems", {
        scope: scope,
        response: response
      });

      try {
        $('[data-toggle="tooltip"]').tooltip(); //$('.collapse').collapse();
      } catch (error) {
        console.log(error);
      }
    },
    getDocHeight: function getDocHeight() {
      var D = document;
      var offset = -60;
      return Math.max(D.body.scrollHeight, D.documentElement.scrollHeight, D.body.offsetHeight, D.documentElement.offsetHeight, D.body.clientHeight, D.documentElement.clientHeight) + offset;
    },
    lerp: function lerp(a, b, c) {
      return a + c * (b - a);
    },
    update: function update() {
      var scope = this;
      scope.events.triggerHandler("update");
    },
    pageY: function pageY(e) {
      if (e !== undefined && e.originalEvent !== undefined && e.originalEvent.touches != undefined && e.originalEvent.touches.length > 0) {
        return e.originalEvent.touches[0].pageY;
      }

      return -1;
    },
    startRender: function startRender() {
      var scope = this;
      scope.isTouchStarted = true;
      scope.pullLength = 0;
      scope.pullStart = 0;
      scope.pullSmooth = 0;
      scope.isTouchDown = false;

      function render() {
        scope.update();
        requestAnimationFrame(render);
      }

      requestAnimationFrame(render);
      scope.events.on("update", function () {
        scope.pullSmooth = scope.lerp(scope.pullSmooth, scope.pullLength, 0.2);
        if (!(scope.pullSmooth > 0.001)) return;
        $("#load-more-icon-bg").css({
          opacity: scope.pullSmooth * 0.1,
          bottom: scope.pullSmooth + "px"
        });
        $("#load-more-icon").css({
          transform: "rotate(" + scope.pullSmooth * 3.0 + "deg)",
          opacity: scope.pullSmooth * 0.01
        });
      });
      $(window).bind("touchstart mousedown", function (e) {
        scope.isTouchStarted = true;
        scope.isTouchDown = true;
      });
      $(window).bind("touchmove mousemove", function (e) {
        var pageY = scope.pageY(e);

        if ($(window).scrollTop() + $(this).height() >= scope.getDocHeight() && scope.isTouchStarted) {
          scope.isTouchStarted = false;
          scope.pullStart = scope.getDocHeight() - ($(window).scrollTop() + $(this).height()) + pageY;
        }

        if (scope.isTouchStarted === false) {
          scope.pullLength = scope.pullStart - (scope.getDocHeight() - ($(window).scrollTop() + $(this).height()) + pageY);

          if (scope.pullLength > 100) {
            scope.pullStart -= scope.pullLength - 100;
            scope.pullLength = 100;
          }

          if (scope.pullLength < 0) {
            scope.pullLength = 0;
          }
        } else {
          scope.pullLength = 0;
        }
      });
      $(window).bind("touchend mouseup", function (e) {
        scope.isTouchStarted = false;

        if (scope.pullLength > 90) {
          scope.events.triggerHandler("scroll_bottom");
        }

        scope.pullLength = 0;
        scope.pullStart = 0;
        scope.isTouchDown = false;
      });
      scope.canLoad = true;
      $(window).scroll(function () {
        if (scope.isTouchDown) return;
        var isGreater = $(window).scrollTop() + $(this).height() >= scope.getDocHeight();
        var isSmaller = $(window).scrollTop() + $(this).height() < scope.getDocHeight();

        if (isGreater && scope.canLoad) {
          scope.canLoad = false;
          scope.events.triggerHandler("scroll_bottom");
        } else if (isSmaller) {
          scope.canLoad = true;
        }
      });
    }
  };
  return PageScroller;
}();

/***/ }),

/***/ "./resources/js/mg/Row.js":
/*!********************************!*\
  !*** ./resources/js/mg/Row.js ***!
  \********************************/
/*! no static exports found */
/***/ (function(module, exports) {

MG.Row = function () {
  function Row(options) {
    this.settings = {
      id: "#table-id",
      html: ""
    };
    jQuery.extend(this.settings, options);
    this.html(this.settings.html);
  }

  Row.prototype = {
    constructor: Row,
    table: function table() {
      return $(this.settings.id);
    },
    loadingShow: function loadingShow() {// var scope = this;
      // $.mobile.loading("show", {
      //     text: "loading more..",
      //     textVisible: true
      // });
    },
    loadingHide: function loadingHide() {// var scope = this;
      // $.mobile.loading("hide");
      // scope.refresh();
      // scope.updatelayout();
    },
    html: function html(value) {
      var scope = this;
      scope.table().html(value);
    },
    append: function append(html) {
      var scope = this;
      scope.table().append(html);
    },
    getItemTemplate: function getItemTemplate(data) {
      var scope = this;
      var borderColor = data.hasOwnProperty("settings") && data.settings.hasOwnProperty("role") ? "tr-" + data.settings.role : "";
      var statusColor = data.status === 0 ? ' style="background-color: #dedede;"' : " ";
      var html = '<tr class="tr-shadow tr-collapse table-row ' + borderColor + '" data-id="' + data.id + '" id="tr-' + data.id + '" data-toggle="collapse" data-target="#collapse-' + data.id + '" aria-expanded="false" aria-controls="collapse-' + data.id + '" ' + statusColor + " >";
      html += '<td style="padding: 10px; "><span class="block-email">' + data.field1 + "</span></td>";
      html += '<td style="padding: 10px;  padding-left: 0;"><span class="text-center">' + data.field2 + "</span></td>";
      var colspan = 3;

      if (data.field3 !== undefined) {
        colspan++;
        html += '<td style="padding: 10px;  padding-left: 0;"><span class="text-center">' + data.field3 + "</span></td>";
      }

      html += '<td style="padding: 10px; padding-left: 0;" ><div class="table-data-feature">';

      if (!(data.hasOwnProperty("settings") && data.settings.hasOwnProperty("statusEnabled") && !data.settings.statusEnabled)) {
        html += '<label class="switch switch-text switch-success ignore-collapse" style="margin-bottom: 0;margin-top: 4px;margin-right: 5px;">';
        var checked = data.status == 1 ? 'checked="true"' : "";
        html += '<input type="checkbox" class="switch-input switch-status-input" data-status="' + data.status + '" data-id="' + data.id + '" ' + checked + ">";
        html += '<span data-on="On" data-off="Off" class="switch-label"></span>';
        html += '<span class="switch-handle"></span></label>';
        html += "";
      }

      if (!(data.hasOwnProperty("settings") && data.settings.hasOwnProperty("editEnabled") && !data.settings.editEnabled)) {
        html += '<button class="item row-button-edit ignore-collapse" data-toggle="tooltip" data-placement="top" title="Edit" data-id="' + data.id + '" ><i class="zmdi zmdi-edit"></i></button>';
      }

      html += "</td></tr>";
      html += '<tr> <td colspan="' + colspan + '" style="margin: 0;padding: 0;">';
      html += '<div class="collapse" id="collapse-' + data.id + '"><div class="card card-body" style="margin: 0;margin-top: 5px;">';
      html += data.more;
      html += "</div></div>";
      html += "</td></tr>";
      html += '<tr class="spacer"></tr>';
      return html;
    },
    getItemNoActionTemplate: function getItemNoActionTemplate(data) {
      var scope = this;
      var borderColor = data.hasOwnProperty("settings") && data.settings.hasOwnProperty("role") ? "tr-" + data.settings.role : "";
      var html = '<tr class="tr-shadow tr-collapse table-row ' + borderColor + '" data-id="' + data.id + '" id="tr-' + data.id + '" data-toggle="collapse" data-target="#collapse-' + data.id + '" aria-expanded="false" aria-controls="collapse-' + data.id + '" >';
      html += '<td style="padding: 10px; "><span class="block-email">' + data.field1 + "</span></td>";
      html += '<td style="padding: 10px;  padding-left: 0; text-align: center;"><span >' + data.field2 + "</span></td>";
      var colspan = 3;

      if (data.field4 !== undefined) {
        html += '<td style="padding: 10px;  padding-left: 0; text-align: center;"><span >' + data.field4 + "</span></td>";
        colspan++;
      }

      if (data.field5 !== undefined) {
        html += '<td style="padding: 10px;  padding-left: 0; text-align: center;"><span >' + data.field5 + "</span></td>";
        colspan++;
      }

      html += '<td style="padding: 10px; padding-left: 0; text-align: right;" >';
      html += data.field3;
      html += "</td></tr>";
      html += '<tr> <td colspan="' + colspan + '" style="margin: 0;padding: 0;">';
      html += '<div class="collapse" id="collapse-' + data.id + '"><div class="card card-body" style="margin: 0;margin-top: 5px;">';
      html += data.more;
      html += "</div></div>";
      html += "</td></tr>";
      html += '<tr class="spacer"></tr>';
      return html;
    }
  };
  return Row;
}();

/***/ }),

/***/ "./resources/sass/app.scss":
/*!*********************************!*\
  !*** ./resources/sass/app.scss ***!
  \*********************************/
/*! no static exports found */
/***/ (function(module, exports) {

// removed by extract-text-webpack-plugin

/***/ }),

/***/ 0:
/*!*************************************************************!*\
  !*** multi ./resources/js/app.js ./resources/sass/app.scss ***!
  \*************************************************************/
/*! no static exports found */
/***/ (function(module, exports, __webpack_require__) {

__webpack_require__(/*! D:\xampp\htdocs\CashPro\Web\cp\resources\js\app.js */"./resources/js/app.js");
module.exports = __webpack_require__(/*! D:\xampp\htdocs\CashPro\Web\cp\resources\sass\app.scss */"./resources/sass/app.scss");


/***/ })

/******/ });