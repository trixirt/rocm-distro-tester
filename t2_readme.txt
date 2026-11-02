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
 structure. We do this using the "source" or "file" command!

 Copy and paste this command to import your schema file:

    \i /mnt/schema.sql

 *Note:* I used a backslash (`\`) followed by 'i'. This tells psql to
 execute the file located at `/mnt/schema.sql`. 

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

 First, look at the CSV file provided in our mounted volume by running
 this command inside psql:

    SELECT pg_read_file('/mnt/distros_seed.csv');

 Now, run this import command to fill your `distros` table:

    COPY distros FROM '/mnt/distros_seed.csv' WITH (FORMAT csv);


 *Crucial Note:* The CSV has 4 columns and the table has 5 (because of the
 auto-generated `id` column). Postgres knows to skip the ID and fill it 
 automatically for us! 

---------------------------------------------------------------------
 Task 4: Querying Your Bootstrapped Data
---------------------------------------------------------------------

 Verify that your "filing cabinet" is now populated with real ROCm data.

 Run this to see what you imported:

    SELECT name, tag, state FROM distros;

 You should see Fedora, Ubuntu, Arch Linux, and others ready for testing!


=====================================================================
 READMEEOF
mv t2_readme.txt ./tutorials/db/2/README.txt
