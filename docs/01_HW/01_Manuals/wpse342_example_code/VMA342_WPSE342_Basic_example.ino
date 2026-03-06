/* 
  @@@@@@@@@@@@@@@@@@@@@@                                                                                                                               
  @@@@@@@@@@@@@@@@@@@@@@             @@@@    @@@    @@@@     @@@@    @@@@        @@@@@@@@@        @@@@@@@@@@@@@@     @@@@@@@@@@@@@@        @@@@@@@@@  
  @@@@@@@@@@@@@@@@@@@@@@             @@@@    @@@    @@@@     @@@@    @@@@       @@@@@@@@@@        @@@@@@@@@@@@@@     @@@@@@@@@@@@@@        @@@@@@@@@  
  @@@@@  @@@  @@@  @@@@@             @@@@    @@@    @@@@     @@@@    @@@@       @@@@   @@@@        @@@@@   @@@@@       @@@@@   @@@@       @@@@   @@@@ 
  @@@@@            @@@@@             @@@@   @@@@    @@@@     @@@@@@@@@@@@       @@@@   @@@@        @@@@@   @@@@@       @@@@@   @@@@       @@@@   @@@@ 
  @@@@@   @    @   @@@@@             @@@@   @@@@    @@@@     @@@@@@@@@@@@       @@@@@@@@@@@        @@@@@   @@@@@       @@@@@   @@@@       @@@@@@@@@@@ 
  @@@@@            @@@@@             @@@@  @@@@@   @@@@@     @@@@    @@@@      @@@@@@@@@@@@       @@@@@@   @@@@@     @@@@@@@   @@@@       @@@@@@@@@@@
  @@@@@@@@@@@@@@@@@@@@@@             @@@@@@@@@@@@@@@@@@@     @@@@    @@@@      @@@@    @@@@@      @@@@@@@@@@@@@@     @@@@@@@@@@@@@@      @@@@     @@@@
  @@@@@@@@@@@@@@@@@@@@@@

  Whadda WPSE342 Air Quality combo board sensor:

  This air quality combo board senses the atmospheric-quality by using the popular CCS811 and BME280 ICs. It provides a variety of environmental data including:
  barometric pressure, humidity, temperature, TVOCs and equivalent CO2 (or eCO2) levels.
  Communication is possible through the I²C protocol.

  The CCS811 is an exceedingly popular sensor, providing readings for equivalent CO2 (or eCO2) in parts per million (PPM)
  and total volatile organic compounds (TVOC) in the parts per billion (PPB).
  The CCS811 also has a feature that allows it to fine-tune its readings if it has access to the current humidity and temperature.
  
   
  Pin Configuration Sensor board to arduino using I²C interface: 
  --------------------------------------------------------------

  WPSE342 | Arduino Uno

  3V3	    =	 3V3 (VCC)
  GND     =	 GND (Ground)
  SDA     =	 UNO SDA (A4) / Mega SDA (44 - IDE 20)    
  SCL	    =	 UNO SCL (A5) / Mega SCL (43 - IDE 21)    
  
  Required Libraries:
  -------------------
  SparkFunBME280.h
  SparkFunCCS811.h
  
  Standard Arduino Library:
  -------------------------
  
  Wire.h

  
  For more informarion about WPSE342 Air Quality sensor, consult the manual at the WPSE342 product page on https://whadda.com/product/air-quality-sensor-combo-board-wpse342/

*/

#include <Wire.h>
#include "SparkFunBME280.h" //Click here to get the library: http://librarymanager/All#SparkFun_BME280
#include "SparkFunCCS811.h" //Click here to get the library: http://librarymanager/All#SparkFun_CCS811

BME280 myBME280;

#define CCS811_ADDR 0x5B //Default I2C Address
//#define CCS811_ADDR 0x5A //Alternate I2C Address

CCS811 myCCS811(CCS811_ADDR);


void setup() {
  
 // Open serial communications and wait for port to open:
  
 Serial.begin(115200);

 Serial.println("Basic Example for reading out data from BME280 and CCS811 sensors");

 Wire.begin();

 if (myBME280.beginI2C() == false) //Begin communication over I2C
  {
    Serial.println("BME280 sensor did not respond. Please check wiring. Freezing...");
    while(1); //Freeze
  }

  myBME280.setReferencePressure(101957); //Adjust the sea level pressure used for altitude calculations

  if (myCCS811.begin() == false)
  {
    Serial.print("CCS811 error did not respond. Please check wiring. Freezing...");
    while (1)
      ;
  }
}

void loop() {
  
  // Print out the raw data of sensors in Float, to serial monitor

  Serial.print("Humidity: ");
  Serial.print(myBME280.readFloatHumidity(), 0);
  Serial.print(" RH%");

  Serial.print(" | Pressure: ");
  Serial.print(myBME280.readFloatPressure() /100.0F, 0);
  Serial.print(" hPa");

  Serial.print(" | Alt: ");
  Serial.print(myBME280.readFloatAltitudeMeters(), 1);  //Show Altitude in meters.
  //Serial.print(myBME280.readFloatAltitudeFeet(), 1);  //Show Altitude in feets.
  Serial.print(" m");

  Serial.print(" | Temp: ");
  //Serial.print(myBME280.readTempF(), 0);  // Show temp. in °Fahrenheit
  Serial.print(myBME280.readTempC(), 0);    // Show temp. in °Celsius
  Serial.print(" °C");

  Serial.println();


  //Check to see if data is ready with .dataAvailable()
  if (myCCS811.dataAvailable())
  {
    //If so, have the sensor read and calculate the results.
    //Get them later
    myCCS811.readAlgorithmResults();

    Serial.print("CO2: ");
    //Returns calculated CO2 reading
    Serial.print(myCCS811.getCO2());
    Serial.print(" ppm");
    Serial.print("     | tVOC: ");
    //Returns calculated TVOC reading
    Serial.print(myCCS811.getTVOC());
    Serial.print(" PPB");
    Serial.println();
  }
  delay(5000); //Don't spam the I2C bus                                 
}
