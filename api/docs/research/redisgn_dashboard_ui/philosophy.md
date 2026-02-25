# UX Philosophy

* We need repeatability for each view

* I don't want user to be confused or overwhelm with info

* Info fetched and presented when needed per basis design

* The ui should visually represent the data npt just "show the data"

  * Examples:

    * creating tree like structure for project nested within

      * even tho in .claude/ it is flat

    * grouping agents in to category of a session

      * so visually user can tell which agent belongs to what type, even tho the agent id is just nuremical

    * Visually user can distinguish between git and non git projects.

      * even tho projects are just directories in local system

# UI Views

### **1> Project View <Individual Project>**

**"Repo/Directory name"** as name

* Tabs

  * Overview

    * Active Branches <only for git projects>

      * The list of branches for the project that sessions within that project interacted with in the last day

    * Working Directory

      * full path in the system for the project

  * Sessions <List of Sessions>

    * Grouped by Branches <for users to visually distinguish between sessions of different branch>

  * Analytics <for the project >

    * Total Sessions

    * Total Cost

    * Total Tokens

    * Total Duration

    * Good interactive graphs and components. to select "over a period" analytics for the above mentioned analytics. So total gives "till date" info and graphs section will provide ability to time box the analytics

### **2> Session View <Individual Session>**

**"Sulg"&#x20;**&#x61;s the name

* Tabs

  * Overview

    * Initial prompt <like we display right now>

    * Active Branche/s <only for session of git project>

      * the branches session interacted with

    * Last Message time "Jan 9, 10am PST"

    * Model used

  * Timeline

    * i like what we have so far

    * look for optimization

  * Files

    * i like what we have so far

    * look for optimization

  * Agents

    * i like what we have so far

  * Analytics

    * Total Cost

    * Total Tokens

    * Total Duration

    * Total Tools

    * Cache Hit Rate

    * Good interactive graphs and components. to select "over a period" analytics for the above mentioned analytics. So total gives "till date" info and graphs section will provide ability to time box the analytics
