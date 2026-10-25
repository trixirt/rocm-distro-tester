=====================================================================
 DATABASE TUTORING: BOOTSTRAPPING & DATA IMPORT (SECTION 7 PREP)
 =====================================================================

 GOAL: Learn how to use the "Schema Source of Truth" and CSV imports.
 
 In a real project, we don't type CREATE TABLE commands by hand. 
 We save them in files and import data like professionals.

---------------------------------------------------------------------
 Task 0: Check Your Environment
---------------------------------------------------------------------

 First, run your `./run.sh` script from Tutorial 2's directory to start
 the database with the necessary mounts (volumes) enabled.

    cd tutorials/db/2
    ./run.sh


---------------------------------------------------------------------
 Task 1: The Schema Source of Truth (`schema.sql`)
---------------------------------------------------------------------

 In production, we use SQL files to version-control our database 
 structure. We do this using the "source" command!

 Copy and paste this command to import your schema file:

    \i /s1.sql

 *Note:* I used a backslash (`\`) followed by 'i'. This tells psql to
 execute the file located at `/s1.sql`. 

---------------------------------------------------------------------
 Task 2: Verify Your Tables (The "Shelves")
---------------------------------------------------------------------

 Check if your tables were created correctly. The `\d+` command gives 
 you a detailed view of exactly what columns and types exist.

 Run this to inspect the `distros` table:

    \d+ distros

 And the `packages` table:

    \d+ packages


---------------------------------------------------------------------
 Task 3: Importing Data (The "Boxes") - Using CSVs
---------------------------------------------------------------------

 Real data lives in spreadsheets. Postgres has a built-in tool called 
 COPY that is much faster and easier than typing INSERT commands.

 Now, run this import command to fill your `distros` table:

    COPY distros(name) FROM '/d1.csv' WITH (FORMAT csv);

---------------------------------------------------------------------
 Task 4: Querying Your Bootstrapped Data
---------------------------------------------------------------------

 Verify that your "filing cabinet" is now populated with real ROCm data.

 Run this to see what you imported:

    SELECT name FROM distros;

 You should see Fedora, Ubuntu, Arch Linux, and others ready for testing!


=====================================================================
