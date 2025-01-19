"use strict";

/*Line chart*/
function lineChart() {
    window.lineChart = Morris.Line({
        element: 'line-example',
        data: [
            { y: '2006', a: 100, b: 90 },
            { y: '2007', a: 75, b: 65 },
            { y: '2008', a: 50, b: 40 },
            { y: '2009', a: 75, b: 65 },
            { y: '2010', a: 50, b: 40 },
            { y: '2011', a: 75, b: 65 },
            { y: '2012', a: 100, b: 90 }
        ],
        xkey: 'y',
        redraw: true,
        ykeys: ['a', 'b'],
        hideHover: 'auto',
        labels: ['Series A', 'Series B'],
        lineColors: ['#B4C1D7', '#FF9F55']
    });
}

/*Area chart*/
function areaChart() {
    window.areaChart = Morris.Area({
        element: 'area-example',
        data: [
            { y: '2006', a: 100, b: 90 },
            { y: '2007', a: 75, b: 65 },
            { y: '2008', a: 50, b: 40 },
            { y: '2009', a: 75, b: 65 },
            { y: '2010', a: 50, b: 40 },
            { y: '2011', a: 75, b: 65 },
            { y: '2012', a: 100, b: 90 }
        ],
        xkey: 'y',
        resize: true,
        redraw: true,
        ykeys: ['a', 'b'],
        labels: ['Series A', 'Series B'],
        lineColors: ['#93EBDD', '#64DDBB']
    });
}

/*Donut chart*/
function donutChart(casinoProfit,liveCasinoProfit,sportsBook,casinoLetplayProfit, casino, liveCasino, sportsbooks, casinoLetplayBook) {
    window.areaChart = Morris.Donut({
        element: 'donut-example',
        redraw: true,
        data: [
            { label: casino, value: casinoProfit },
            { label: liveCasino, value: liveCasinoProfit },
            { label: sportsbooks, value: sportsBook },
			{ label: casinoLetplayBook, value: casinoLetplayProfit }
        ],
        colors: ['#5FBEAA', '#34495E', '#FF9F55', '#7E81CB']
    });
}

// Morris bar chart
// Morris.Bar({
//     element: 'morris-bar-chart',
//     data: [{
//         y: '2006',
//         a: 100,
//         b: 90,
//         c: 60
//     }, {
//         y: '2007',
//         a: 75,
//         b: 65,
//         c: 40
//     }, {
//         y: '2008',
//         a: 50,
//         b: 40,
//         c: 30
//     }, {
//         y: '2009',
//         a: 75,
//         b: 65,
//         c: 100
//     }, {
//         y: '2010',
//         a: 50,
//         b: 40,
//         c: 30
//     }, {
//         y: '2011',
//         a: 75,
//         b: 65,
//         c: 40
//     }, {
//         y: '2012',
//         a: 100,
//         b: 90,
//         c: 40
//     }],
//     xkey: 'y',
//     ykeys: ['a', 'b', 'c'],
//     labels: ['A', 'B', 'C'],
//     barColors: ['#5FBEAA', '#5D9CEC', '#cCcCcC'],
//     hideHover: 'auto',
//     gridLineColor: '#eef0f2',
//     resize: true
// });

// Extra chart
function extraAreaChart(profits, dates) {
    const data = [];
    for (let i = 0; i < dates.length; i++) {
      data.push({
        period: dates[i],
        profit: profits[i]
      });
    }
  
    Morris.Area({
      element: 'morris-extra-area',
      data: data.reverse(),
      lineColors: ['#7E81CB'],
      parseTime: false,
      xkey: 'period',
      ykeys: ['profit'],
      labels: ['Lucro'],
      pointSize: 0,
      lineWidth: 0,
      resize: true,
      fillOpacity: 0.8,
      behaveLikeLine: true,
      gridLineColor: '#34495E',
      hideHover: 'auto'
    });
  }