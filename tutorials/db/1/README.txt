=====================================================================
 DATABASE TUTORING: THE SQL WORKOUT (SECTION 7 FOCUS)
 =====================================================================

 GOAL: Learn to manage a Postgres database from the inside out.

 NOTE: This tutorial treats PostgreSQL like a filing cabinet. We will
       create this "cabinet" using Docker so you can experiment without
       risking your actual computer files.


---------------------------------------------------------------------
 Task 0: 'Hello World' & Exploration
---------------------------------------------------------------------
 Before we touch any files, let's look around our new database room to
 verify it is healthy and empty. These commands check the system state 
 without depending on a specific database being open.

 1. Check who you are logged in as:
    Type this command to see which user you are connected as (we
     configured "mydbuser" via our environment variables).

        SELECT current_user;


 2. Check what folders (Tables) exist right now:  
    In SQL, data is organized into "Tables." A fresh database has NO 
     tables yet—it's a blank filing cabinet waiting for shelves. 

    Run this to verify your room is empty:

        \dt

   *(Output should say "No relations found")*


---------------------------------------------------------------------
 Task 1: Creating your First Table (The Structure)
---------------------------------------------------------------------
 We need to build the physical shelves that will hold our ROCm package 
 data. We will create a table called "packages" with two slots: one for
  the name and one for the version number.

    Copy and paste this:


        CREATE TABLE packages (
            name text PRIMARY KEY, 
            version text
        );


   *Note on PRIMARY KEY: This ensures that every row in our cabinet has*
   *a unique 'name'. You cannot have two products with the same ID.* 


---------------------------------------------------------------------
 Task 2: Adding ROCm Data (The "Write")
---------------------------------------------------------------------
 Now let's populate the database with three specific builds from your
 tracker list. 

    Copy and paste these into your terminal:


        INSERT INTO packages (name, version) VALUES ('hipblas', '10.1.0');
        INSERT INTO packages (name, version) VALUES ('rocm-examples', '7.2.1');
        INSERT INTO packages (name, version) VALUES ('rccl', '10.0.2');


---------------------------------------------------------------------
 Task 3: Querying the Database (The "Read") 
---------------------------------------------------------------------
 Now we act as a user looking for data. We want to see exactly what is
 inside our filing cabinet right now. 

    Run this query:

        SELECT * FROM packages;


    Expected Result: You should see a list of all three packages and their 
          respective versions on your screen.


---------------------------------------------------------------------
 Task 4: Filtering for Specific Data
---------------------------------------------------------------------
 Now let's be more specific. We only want to see if "hipblas" exists 
 and what version it is. We use the WHERE clause like an advanced 
 phonebook lookup.

    Run Task 3 again, but add these words to the very end of your query:


        ... WHERE name = 'hipblas'


    (The full command should look like: SELECT * FROM packages WHERE
     name = 'hipblas'; )


---------------------------------------------------------------------
 Task 5: Querying for a Non-Existent Package ("Silent" Error)
---------------------------------------------------------------------
 Often in programming, we assume missing data will crash the program or 
 give us an error. In SQL, if you ask for something that doesn't exist,
 it simply returns nothing—it stays silent! 

    Try querying for "rocbl" (which we did not add to our list):

        SELECT * FROM packages WHERE name = 'rocbl';


---------------------------------------------------------------------
 Task 6: Updating Data (The "Update" Command)
---------------------------------------------------------------------
 The "rccl" package had an issue, so we need to change the status without 
 deleting it from our file cabinet.

    Run Task 3 again, but change your command to this one instead:

        UPDATE packages 
        SET version = '10.1.0' 
        WHERE name='rccl';


   (Now run SELECT * FROM packages; and you will see only "rccl" has
   changed!)


---------------------------------------------------------------------
 Task 7: Exiting from SQL
---------------------------------------------------------------------
 When you are done learning, don't just close the terminal window! If you do, 
 your database office will stay open in the background.

 To properly sign out of your session while keeping the data safe:

     \q

 This command sends you back to your computer's regular command prompt.


=====================================================================
