i worked with mock data in first to start early 
i searched for 3d model for the visulization map 
draw the map of usa 
the team planned for the kpis then i applied it in the dashboard with mock data

make scripts to test connection with the kafka and the warehouse 

found some errors in the data and returned to edit it in the warehouse 

we planned for the full flow for the streaming for how to view it and we planned to do (.kafka plan ....)

how is the data flow from streaming till it reach the dashboard and the system architecture 

make the page refresh after 30 min to get if there is new data 

write the kpis sql queries that will run on the warehouse from the backend

removed all the mock data: the dashboard now reads only the backend (warehouse KPIs + kafka live stream) 


all times on the dashboard are shown in cairo time (data stays utc): live map, alerts, last updated, cold-chain chart, stream kpi period, delay by hour chart
removed the "cairo" word from the screen: cairo is the default time so times show without a label
